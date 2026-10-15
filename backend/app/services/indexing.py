"""Indexing: turn a stored memory into searchable chunks and vectors.

Plain English: chunks and embeddings are **derived data**. They can always be
rebuilt from ``memories.normalized_content``, so this module is the one place
that keeps the retrieval index in step with the stored memories.

Why this exists as its own step: indexing needs the local embedding model, which
may not be installed. Ingestion must never fail because of that — saving a
memory is the important part. So indexing is explicit and separate:

* ``index_memory`` indexes one memory and reports what happened.
* ``index_pending_memories`` sweeps memories that have chunks with no vector,
  which is how an existing database gets indexed after installing the model.
* ``remove_memory`` drops a memory's chunks and vectors.

Idempotence: re-indexing unchanged content produces the same stable chunk ids
and replaces the rows rather than duplicating them, so running it repeatedly is
safe. A memory whose embedding fails is left unindexed (not partially indexed),
so a later run retries it cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, settings
from app.repositories.chunk_store import ChunkRepository
from app.repositories.sqlite_store import MemoryRepository
from app.repositories.vector_store import VectorStore
from app.services.chunking import chunk_text
from app.services.embeddings import (
    EmbeddingInputError,
    EmbeddingModelUnavailableError,
    EmbeddingResponseError,
    EmbeddingService,
)

#: Why a memory was not indexed. Callers map these onto HTTP codes.
INDEXED = "indexed"
SKIPPED_EMPTY = "skipped_empty_text"
SKIPPED_UNAVAILABLE = "skipped_model_unavailable"


class IndexingUnavailableError(RuntimeError):
    """The local embedding model could not be reached."""


@dataclass(frozen=True)
class IndexOutcome:
    """The result of indexing one memory."""

    memory_id: str
    status: str
    chunk_count: int = 0
    detail: str = ""

    @property
    def indexed(self) -> bool:
        return self.status == INDEXED


class IndexingService:
    """Builds and maintains the chunk + vector index for stored memories."""

    def __init__(
        self,
        memories: MemoryRepository,
        chunks: ChunkRepository,
        vectors: VectorStore,
        embeddings: Optional[EmbeddingService] = None,
        config: Settings = settings,
    ) -> None:
        self._memories = memories
        self._chunks = chunks
        self._vectors = vectors
        self._embeddings = embeddings or EmbeddingService(config=config)
        self._config = config

    def index_memory(self, memory_id: str) -> IndexOutcome:
        """Chunk and embed one memory.

        Returns an outcome rather than raising for the expected "nothing to do"
        cases, so a caller can sweep a whole database without one odd memory
        aborting the run. Only a genuinely unreachable model raises.
        """
        record = self._memories.get_by_id(memory_id)
        if record is None:
            raise IndexingUnavailableError(f"Memory {memory_id} does not exist.")
        if not record.normalized_text.strip():
            return IndexOutcome(
                memory_id, SKIPPED_EMPTY, detail="This memory has no text to index."
            )

        pieces = chunk_text(
            record.normalized_text,
            record.id,
            chunk_size=self._config.rag_chunk_size,
            overlap=self._config.rag_chunk_overlap,
        )
        if not pieces:
            return IndexOutcome(memory_id, SKIPPED_EMPTY, detail="No chunks were produced.")

        # Embed first: a failure here must leave no half-written index behind.
        try:
            vectors = self._embeddings.embed_batch([piece.text for piece in pieces])
        except EmbeddingInputError as exc:
            return IndexOutcome(memory_id, SKIPPED_EMPTY, detail=str(exc))
        except (EmbeddingModelUnavailableError, EmbeddingResponseError) as exc:
            raise IndexingUnavailableError(str(exc)) from exc

        # Replace chunks transactionally, then upsert the matching vectors.
        chunk_ids = self._chunks.replace_memory_chunks(record.id, pieces)
        self._vectors.upsert_many(
            [
                (chunk_id, record.id, list(vector))
                for chunk_id, vector in zip(chunk_ids, vectors)
            ],
            self._embeddings.model,
        )
        return IndexOutcome(memory_id, INDEXED, chunk_count=len(chunk_ids))

    def index_pending_memories(self, limit: int = 100) -> list:
        """Index every memory that is missing chunks or vectors.

        This is how an existing database is brought up to date after the
        embedding model is installed, and how newly ingested memories (which are
        stored but deliberately not indexed inline) become searchable. Memories
        that cannot be indexed are reported, not raised, so the sweep completes.
        """
        sessions: Optional[sessionmaker] = getattr(self._vectors, "_sessions", None)
        if sessions is None:
            raise IndexingUnavailableError("Indexing needs a bound session factory.")

        outcomes: list = []
        for memory_id in self._pending_memory_ids(sessions, limit):
            try:
                outcomes.append(self.index_memory(memory_id))
            except IndexingUnavailableError as exc:
                outcomes.append(
                    IndexOutcome(memory_id, SKIPPED_UNAVAILABLE, detail=str(exc))
                )
                break  # the model is unreachable; sweeping further is pointless
        return outcomes

    def _pending_memory_ids(self, sessions: sessionmaker, limit: int) -> list:
        """Memory ids that need indexing, in stable order.

        Two situations count as pending:

        1. a memory with no chunks at all (freshly ingested, never indexed), and
        2. a memory with chunks but no vector for them (indexing was interrupted,
           or the embedding model has changed).
        """
        from sqlalchemy import text

        session = sessions()
        try:
            rows = session.execute(
                text(
                    "SELECT memories.id AS memory_id FROM memories "
                    "LEFT JOIN memory_chunks AS chunk ON chunk.memory_id = memories.id "
                    "LEFT JOIN chunk_embeddings AS emb ON emb.chunk_id = chunk.id "
                    "WHERE chunk.id IS NULL OR emb.chunk_id IS NULL "
                    "GROUP BY memories.id "
                    "ORDER BY memories.id LIMIT :limit"
                ),
                {"limit": limit},
            ).all()
            return [row[0] for row in rows]
        finally:
            session.close()

    def remove_memory(self, memory_id: str) -> int:
        """Drop a memory's chunks (and, by cascade, its vectors).

        Memory deletion already cascades at the database level; this exists for
        reindexing a single memory without deleting it.
        """
        return self._chunks.delete_memory_chunks(memory_id)


