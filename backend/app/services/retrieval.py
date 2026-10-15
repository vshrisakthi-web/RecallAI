"""Semantic retrieval for user questions (Module 6, Task 6.4).

Plain English: turn "What did I learn about RAG last week?" into ranked
evidence. The flow is: validate the question -> extract the time window
("last week") -> embed the full question text locally -> cosine-search the
chunk vectors -> keep only the active model generation, the similarity
floor, and the date window -> join each surviving chunk to its real memory
and source rows -> return grounded evidence.

Deleted memories can never appear: they cascade-delete their chunks and
vectors at the database level, and the assembly join requires the memory
row to exist — a hit whose memory is gone is skipped, never returned.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable, Optional

import httpx
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, settings
from app.repositories.base import StorageError
from app.repositories.chunk_store import ChunkRepository
from app.repositories.sqlite_store import MemoryRepository
from app.repositories.vector_store import VectorStore
from app.services.embeddings import (
    EmbeddingInputError,
    EmbeddingModelUnavailableError,
    EmbeddingResponseError,
    EmbeddingService,
)
from app.services.temporal import (
    NormalizedQuery,
    QueryInputError,
    TemporalFilter,
    normalize_and_parse,
)


class RetrievalInputError(ValueError):
    """Raised for empty/oversized questions and invalid date filters."""


class RetrievalUnavailableError(RuntimeError):
    """Raised when the embedding model or vector index cannot serve a query."""


@dataclass(frozen=True)
class Evidence:
    """One grounded evidence passage. Every field comes from stored rows."""

    chunk_id: str
    memory_id: str
    passage: str
    source_id: Optional[str]
    source_type: Optional[str]
    source_title: Optional[str]
    source_url: Optional[str]
    domain: Optional[str]
    captured_at: Optional[datetime]
    similarity: float


@dataclass(frozen=True)
class RetrievalResult:
    """The full answer to one retrieval call (before any LLM is involved)."""

    query: NormalizedQuery
    evidence: list[Evidence]
    candidates_considered: int
    temporal: Optional[TemporalFilter]

class SemanticRetrievalService:
    """Embed-then-search retrieval with grounded evidence assembly.

    Dependencies are injected (repositories, embedding service, clock) so
    tests run fully offline with deterministic vectors and timestamps.
    """

    def __init__(
        self,
        memories: MemoryRepository,
        chunks: ChunkRepository,
        vectors: VectorStore,
        embeddings: Optional[EmbeddingService] = None,
        config: Settings = settings,
        now: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._memories = memories
        self._chunks = chunks
        self._vectors = vectors
        self._embeddings = embeddings or EmbeddingService(config=config)
        self._config = config
        self._now = now or (lambda: datetime.now(timezone.utc))

    # --- Public API --------------------------------------------------------

    def retrieve(
        self,
        question: object,
        top_k: Optional[int] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> RetrievalResult:
        """Rank evidence for a question, honoring temporal filters.

        The date window comes from the caller OR from the question text
        ("last week"), never both silently: an explicit caller filter wins,
        and the parsed expression is still reported for transparency. Date
        bounds are inclusive on both ends, matching the memories list API.
        """
        if from_date is not None and to_date is not None and from_date > to_date:
            raise RetrievalInputError("from_date must not be after to_date.")
        try:
            query = normalize_and_parse(question, self._now())
        except QueryInputError as exc:
            raise RetrievalInputError(str(exc)) from exc

        temporal = query.temporal
        effective_from = from_date if from_date is not None else (
            temporal.from_date if temporal else None
        )
        effective_to = to_date if to_date is not None else (
            temporal.to_date if temporal else None
        )

        try:
            query_vector = self._embeddings.embed_query(query.text)
        except EmbeddingInputError as exc:
            raise RetrievalInputError(str(exc)) from exc
        except (EmbeddingModelUnavailableError, EmbeddingResponseError) as exc:
            raise RetrievalUnavailableError(
                "The local embedding model is unavailable."
            ) from exc
        except httpx.HTTPError as exc:
            raise RetrievalUnavailableError(
                "The local embedding model could not be reached."
            ) from exc

        limit = self._config.rag_candidates_per_channel
        try:
            hits = self._vectors.search(
                query_vector,
                self._embeddings.model,
                top_k=limit,
                min_similarity=self._config.rag_min_similarity,
            )
        except StorageError as exc:
            raise RetrievalUnavailableError(
                "The vector index could not be searched."
            ) from exc

        evidence: list[Evidence] = []
        kept = top_k if top_k is not None else self._config.rag_top_k
        for hit in hits:
            item = self._assemble(hit.chunk_id, hit.memory_id, hit.score)
            if item is None:
                continue  # memory or chunk gone — skip, never fabricate
            if not self._in_window(item.captured_at, effective_from, effective_to):
                continue
            evidence.append(item)
            if len(evidence) >= max(kept, 0):
                break
        return RetrievalResult(
            query=query,
            evidence=evidence,
            candidates_considered=len(hits),
            temporal=temporal,
        )

    # --- Assembly ----------------------------------------------------------

    def _assemble(
        self, chunk_id: str, memory_id: str, similarity: float
    ) -> Optional[Evidence]:
        """Join one vector hit to its chunk, memory, and source rows."""
        try:
            chunk = self._chunks.get_by_id(chunk_id)
        except StorageError:
            return None
        if chunk is None or chunk.memory_id != memory_id:
            return None
        try:
            record = self._memories.get_by_id(memory_id)
        except StorageError:
            return None
        if record is None:
            return None  # deleted memory — excluded at the retrieval layer
        return Evidence(
            chunk_id=chunk.id,
            memory_id=memory_id,
            passage=chunk.chunk_text,
            source_id=chunk.source_id,
            source_type=(
                str(record.source_type)
                if not hasattr(record.source_type, "value")
                else record.source_type.value
            ),
            source_title=record.title or None,
            source_url=record.source_url,
            domain=record.domain,
            captured_at=record.captured_at,
            similarity=similarity,
        )

    @staticmethod
    def _in_window(
        captured: Optional[datetime],
        from_date: Optional[date],
        to_date: Optional[date],
    ) -> bool:
        if from_date is None and to_date is None:
            return True
        if captured is None:
            return False  # no event time: cannot claim it fits the window
        day = captured.astimezone(timezone.utc).date()
        if from_date is not None and day < from_date:
            return False
        if to_date is not None and day > to_date:
            return False
        return True

