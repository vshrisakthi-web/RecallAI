"""Hybrid keyword + semantic retrieval with reciprocal rank fusion (Task 6.5).

Plain English: one search method is never enough on its own.

  * **Semantic** (cosine over embeddings) understands meaning — ask "how do I
    store vectors?" and it finds a note about "embedding indexes" that never
    uses those words. But it is weak on rare, exact tokens.
  * **Keyword** (BM25 over the chunk FTS index) nails exact tokens — "HNSW",
    "Ollama", "sqlite-vec" — but a paraphrase slips straight past it.

Hybrid retrieval runs both channels and merges them with **Reciprocal Rank
Fusion** (see ``app.services.evidence.fuse_rankings``). Each channel supplies an
ordered list; a chunk found by both gets credit from both, so agreement between
two independent methods is rewarded instead of one method's raw score winning.

Three guarantees worth stating explicitly:

1. **Consistent filtering.** The same validated question, the same temporal
   window, and the same deletion rule apply to *both* channels, so a memory can
   never appear in one channel and be invisible in the other.
2. **One channel failing is survivable.** If the keyword index is unavailable,
   the semantic result is still returned and ``channels`` records that keyword
   did not contribute — a degraded answer, never a fabricated or empty one.
   Symmetrically, an embedding outage leaves the keyword result intact.
3. **Determinism.** Equal inputs produce an equal ranking every time: RRF uses
   only rank positions, and ties break on chunk id.

This module performs retrieval only. It never generates an answer (that is a
separate, later concern) and never invents citations.
"""

from __future__ import annotations

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
from app.services.evidence import (
    KEYWORD_CHANNEL,
    SEMANTIC_CHANNEL,
    Evidence,
    RetrievalInputError,
    RetrievalResult,
    RetrievalUnavailableError,
    assemble_evidence,
    effective_window,
    fuse_rankings,
    in_window,
)
from app.services.keyword_search import KeywordSearchService
from app.services.temporal import normalize_and_parse


class HybridRetrievalService:
    """Keyword + semantic retrieval fused with reciprocal rank fusion.

    Dependencies (repositories, embedding service, clock) are injected so the
    whole suite runs offline with deterministic vectors and timestamps.
    """

    def __init__(
        self,
        memories: MemoryRepository,
        chunks: ChunkRepository,
        vectors: VectorStore,
        embeddings: Optional[EmbeddingService] = None,
        keywords: Optional[KeywordSearchService] = None,
        sessions: Optional[sessionmaker] = None,
        config: Settings = settings,
        now: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._memories = memories
        self._chunks = chunks
        self._vectors = vectors
        self._embeddings = embeddings or EmbeddingService(config=config)
        self._config = config
        self._now = now or (lambda: datetime.now(timezone.utc))
        # The keyword channel needs a session factory. Prefer an explicit one,
        # then the vector store's, so both channels read the same database.
        factory = sessions or getattr(self._vectors, "_sessions", None)
        if factory is None:
            raise RetrievalUnavailableError(
                "The keyword channel needs a session factory bound to the database."
            )
        self._keywords = keywords or KeywordSearchService(factory)

    # --- Public API --------------------------------------------------------

    def retrieve(
        self,
        question: object,
        top_k: Optional[int] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> RetrievalResult:
        """Rank hybrid evidence for a question.

        The date window comes from the caller OR from the question text
        ("last week"), never both silently: an explicit caller filter wins,
        and the parsed expression is still reported for transparency. The
        same effective window applies to both channels, so a memory can
        never surface in one channel and be filtered from the other. Bounds
        are inclusive on both ends, matching the memories list API.
        """
        try:
            query = normalize_and_parse(question, self._now())
        except Exception as exc:  # QueryInputError
            raise RetrievalInputError(str(exc)) from exc

        temporal = query.temporal
        window_from, window_to = effective_window(from_date, to_date, temporal)

        channels: list[str] = []
        candidates_considered = 0

        # --- Semantic channel ---------------------------------------------
        semantic_hits: list[tuple[str, str, float]] = []
        try:
            query_vector = self._embeddings.embed_query(query.text)
            hits = self._vectors.search(
                query_vector,
                self._embeddings.model,
                top_k=self._config.rag_candidates_per_channel,
                min_similarity=self._config.rag_min_similarity,
            )
            semantic_hits = [(hit.chunk_id, hit.memory_id, hit.score) for hit in hits]
            candidates_considered += len(hits)
            channels.append(SEMANTIC_CHANNEL)
        except EmbeddingInputError as exc:
            raise RetrievalInputError(str(exc)) from exc
        except (
            EmbeddingModelUnavailableError,
            EmbeddingResponseError,
            httpx.HTTPError,
        ):
            # The keyword channel can still answer on its own. Only fail when
            # keyword cannot help either (no keyword weight configured).
            if self._config.rag_keyword_weight <= 0:
                raise RetrievalUnavailableError(
                    "The local embedding model is unavailable."
                ) from None
        except StorageError as exc:
            raise RetrievalUnavailableError(
                "The vector index could not be searched."
            ) from exc

        # --- Keyword channel ----------------------------------------------
        keyword_hits: list[tuple[str, str, int]] = []
        try:
            found = self._keywords.search(
                query.text,
                limit=self._config.rag_candidates_per_channel,
                from_date=window_from,
                to_date=window_to,
            )
            keyword_hits = [(hit.chunk_id, hit.memory_id, hit.rank) for hit in found]
            candidates_considered += len(found)
            channels.append(KEYWORD_CHANNEL)
        except StorageError:
            # Degrade to semantic-only rather than failing the whole question.
            if not semantic_hits:
                raise RetrievalUnavailableError(
                    "Neither retrieval channel could serve this question."
                ) from None

        fused = fuse_rankings(
            semantic_hits,
            keyword_hits,
            semantic_weight=self._config.rag_semantic_weight,
            keyword_weight=self._config.rag_keyword_weight,
            rrf_k=self._config.rrf_k,
        )

        kept = top_k if top_k is not None else self._config.rag_top_k
        evidence: list[Evidence] = []
        for candidate in fused:
            item = assemble_evidence(
                candidate.chunk_id,
                candidate.memory_id,
                candidate.similarity,
                self._chunks,
                self._memories,
                keyword_rank=candidate.keyword_rank,
            )
            if item is None:
                continue  # memory or chunk gone — skip, never fabricate
            if not in_window(item.captured_at, window_from, window_to):
                continue
            evidence.append(
                Evidence(
                    chunk_id=item.chunk_id,
                    memory_id=item.memory_id,
                    passage=item.passage,
                    source_id=item.source_id,
                    source_type=item.source_type,
                    source_title=item.source_title,
                    source_url=item.source_url,
                    domain=item.domain,
                    captured_at=item.captured_at,
                    similarity=item.similarity,
                    keyword_rank=item.keyword_rank,
                    score=candidate.score,
                    matched_by=candidate.matched_by,
                )
            )
            if len(evidence) >= max(kept, 0):
                break

        return RetrievalResult(
            query=query,
            evidence=evidence,
            candidates_considered=candidates_considered,
            temporal=temporal,
            channels=tuple(channels),
        )

