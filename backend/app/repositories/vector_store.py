"""Embedding persistence and similarity search (Module 6, Task 6.3).

The smallest reliable solution for this project's scale: vectors live in the
existing SQLite database (``chunk_embeddings`` table) and search is a
brute-force cosine scan. See ``app.services.vectors`` for why NumPy, a vector
extension, and ANN indexes were deliberately avoided, and where the
documented O(n·d) limit sits.

Every stored vector carries its ``model`` and ``dims``. Search only compares
vectors from the active model generation — stale rows (different model or
dimensions) are excluded from ranking and reported through
``stale_count()``/``stale_chunk_ids()`` so the indexing service can reindex
them explicitly. Vectors from incompatible models are never silently mixed.

Deletion needs no code here: both foreign keys are ``ON DELETE CASCADE`` and
the engine enables ``PRAGMA foreign_keys=ON``, so deleting a memory purges
its chunks and their vectors atomically.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.database.models import ChunkEmbedding
from app.repositories.base import StorageError
from app.services.vectors import cosine_similarity, pack_vector, unpack_vector


@dataclass(frozen=True)
class VectorHit:
    """One similarity-search result. Raw vectors never leave the store."""

    chunk_id: str
    memory_id: str
    score: float


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VectorStore:
    """Persisted-vector index bound to one session factory.

    The interface (upsert / get / search / delete / stale detection) is what
    callers depend on — swapping brute force for an ANN index later only
    changes this class.
    """

    def __init__(self, sessions: sessionmaker):
        self._sessions = sessions

    def upsert(
        self, chunk_id: str, memory_id: str, vector: list[float], model: str
    ) -> None:
        """Insert or replace one chunk's vector for the active model."""
        session = self._sessions()
        try:
            existing = session.get(ChunkEmbedding, chunk_id)
            blob = pack_vector(vector)
            if existing is None:
                session.add(
                    ChunkEmbedding(
                        chunk_id=chunk_id,
                        memory_id=memory_id,
                        vector=blob,
                        dims=len(vector),
                        model=model,
                        created_at=_utcnow(),
                        updated_at=_utcnow(),
                    )
                )
            else:
                existing.memory_id = memory_id
                existing.vector = blob
                existing.dims = len(vector)
                existing.model = model
                existing.updated_at = _utcnow()
            session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            raise StorageError("embedding persistence failed") from exc
        finally:
            session.close()

    def upsert_many(
        self, rows: list[tuple[str, str, list[float]]], model: str
    ) -> int:
        """Insert or replace a batch; returns the stored row count."""
        if not rows:
            return 0
        session = self._sessions()
        try:
            for chunk_id, memory_id, vector in rows:
                existing = session.get(ChunkEmbedding, chunk_id)
                blob = pack_vector(vector)
                if existing is None:
                    session.add(
                        ChunkEmbedding(
                            chunk_id=chunk_id,
                            memory_id=memory_id,
                            vector=blob,
                            dims=len(vector),
                            model=model,
                            created_at=_utcnow(),
                            updated_at=_utcnow(),
                        )
                    )
                else:
                    existing.memory_id = memory_id
                    existing.vector = blob
                    existing.dims = len(vector)
                    existing.model = model
                    existing.updated_at = _utcnow()
            session.commit()
            return len(rows)
        except SQLAlchemyError as exc:
            session.rollback()
            raise StorageError("embedding persistence failed") from exc
        finally:
            session.close()

    def get(self, chunk_id: str) -> Optional[ChunkEmbedding]:
        session = self._sessions()
        try:
            return session.get(ChunkEmbedding, chunk_id)
        except SQLAlchemyError as exc:
            raise StorageError("embedding lookup failed") from exc
        finally:
            session.close()

    def delete_by_chunk(self, chunk_id: str) -> bool:
        session = self._sessions()
        try:
            row = session.get(ChunkEmbedding, chunk_id)
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True
        except SQLAlchemyError as exc:
            session.rollback()
            raise StorageError("embedding deletion failed") from exc
        finally:
            session.close()

    def delete_by_memory(self, memory_id: str) -> int:
        """Purge a memory's vectors (defensive; FK cascade covers deletes)."""
        session = self._sessions()
        try:
            result = session.execute(
                delete(ChunkEmbedding).where(
                    ChunkEmbedding.memory_id == memory_id
                )
            )
            session.commit()
            return result.rowcount or 0
        except SQLAlchemyError as exc:
            session.rollback()
            raise StorageError("embedding deletion failed") from exc
        finally:
            session.close()

    def count(self, model: Optional[str] = None) -> int:
        session = self._sessions()
        try:
            stmt = select(func.count()).select_from(ChunkEmbedding)
            if model is not None:
                stmt = stmt.where(ChunkEmbedding.model == model)
            return session.scalar(stmt) or 0
        except SQLAlchemyError as exc:
            raise StorageError("embedding count failed") from exc
        finally:
            session.close()

    # --- Stale-vector detection -----------------------------------------

    def stale_chunk_ids(self, active_model: str, active_dims: int) -> list[str]:
        """Chunk ids whose vectors belong to an older model generation."""
        session = self._sessions()
        try:
            rows = session.scalars(
                select(ChunkEmbedding.chunk_id).where(
                    (ChunkEmbedding.model != active_model)
                    | (ChunkEmbedding.dims != active_dims)
                )
            ).all()
            return sorted(str(chunk_id) for chunk_id in rows)
        except SQLAlchemyError as exc:
            raise StorageError("stale embedding lookup failed") from exc
        finally:
            session.close()

    # --- Similarity search -----------------------------------------------

    def search(
        self,
        query: list[float],
        model: str,
        top_k: int = 6,
        min_similarity: Optional[float] = None,
    ) -> list[VectorHit]:
        """Cosine similarity ranking over the active model generation.

        Only rows matching ``model`` *and* the query's dimensions compete;
        stale rows are silently excluded here (reported via
        ``stale_chunk_ids``). Ties break deterministically by chunk id so
        equal inputs give equal rankings. Returns at most ``top_k`` hits.
        """
        if not query:
            raise StorageError("cannot search with an empty query vector")
        dims = len(query)
        session = self._sessions()
        try:
            rows = session.scalars(
                select(ChunkEmbedding).where(
                    ChunkEmbedding.model == model,
                    ChunkEmbedding.dims == dims,
                )
            ).all()
            scored: list[VectorHit] = []
            for row in rows:
                try:
                    stored = unpack_vector(row.vector, row.dims)
                except ValueError:
                    continue  # one corrupt blob must not fail the search
                score = cosine_similarity(query, stored)
                if min_similarity is not None and score < min_similarity:
                    continue
                scored.append(
                    VectorHit(
                        chunk_id=row.chunk_id,
                        memory_id=row.memory_id,
                        score=score,
                    )
                )
            scored.sort(key=lambda hit: (-hit.score, hit.chunk_id))
            return scored[: max(top_k, 0)]
        except SQLAlchemyError as exc:
            raise StorageError("similarity search failed") from exc
        finally:
            session.close()

