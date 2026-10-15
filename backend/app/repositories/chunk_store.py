"""Chunk persistence: idempotent replace, reads, and memory lifecycle sync.

Chunk rows are derived data rebuilt from ``memories.normalized_content``. The
store never edits the memory record itself. Replacing a memory's chunks is a
single transaction: delete-then-insert, so unchanged content reproduces
identical rows (stable ids) and changed content swaps rows atomically. Memory
deletion cascades to chunks via the foreign key; the store-level ``delete``
exists so the indexing service can purge chunks without touching memories.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import Memory, MemoryChunk
from app.repositories.base import StorageError
from app.services.chunking import TextChunk


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ChunkRepository:
    """Transactional chunk persistence bound to one session factory."""

    def __init__(self, sessions: sessionmaker):
        self._sessions = sessions

    def replace_memory_chunks(
        self, memory_id: str, chunks: list[TextChunk]
    ) -> list[str]:
        """Atomically replace a memory's chunks; return stored chunk ids."""
        session = self._sessions()
        try:
            session.execute(
                delete(MemoryChunk).where(MemoryChunk.memory_id == memory_id)
            )
            memory = session.get(Memory, memory_id)
            source_id = memory.source_id if memory is not None else None
            stored: list[str] = []
            for chunk in chunks:
                session.add(
                    MemoryChunk(
                        id=chunk.chunk_id,
                        memory_id=memory_id,
                        source_id=source_id,
                        chunk_index=chunk.chunk_index,
                        start_offset=chunk.start_offset,
                        end_offset=chunk.end_offset,
                        chunk_text=chunk.text,
                        content_hash=chunk.content_hash,
                        strategy=chunk.strategy,
                        strategy_version=chunk.strategy_version,
                        created_at=_utc_now(),
                        updated_at=_utc_now(),
                    )
                )
                stored.append(chunk.chunk_id)
            session.commit()
            return stored
        except SQLAlchemyError as exc:
            session.rollback()
            raise StorageError("chunk persistence failed") from exc
        finally:
            session.close()

    def delete_memory_chunks(self, memory_id: str) -> int:
        """Remove all chunks for a memory; returns the deleted row count."""
        session = self._sessions()
        try:
            result = session.execute(
                delete(MemoryChunk).where(MemoryChunk.memory_id == memory_id)
            )
            session.commit()
            return result.rowcount or 0
        except SQLAlchemyError as exc:
            session.rollback()
            raise StorageError("chunk deletion failed") from exc
        finally:
            session.close()

    def get_chunks(self, memory_id: str) -> list[MemoryChunk]:
        session = self._sessions()
        try:
            return list(
                session.scalars(
                    select(MemoryChunk)
                    .where(MemoryChunk.memory_id == memory_id)
                    .order_by(MemoryChunk.chunk_index)
                ).all()
            )
        except SQLAlchemyError as exc:
            raise StorageError("chunk lookup failed") from exc
        finally:
            session.close()

    def get_by_id(self, chunk_id: str) -> Optional[MemoryChunk]:
        session = self._sessions()
        try:
            return session.get(MemoryChunk, chunk_id)
        except SQLAlchemyError as exc:
            raise StorageError("chunk lookup failed") from exc
        finally:
            session.close()

    def count_chunks(self, memory_id: Optional[str] = None) -> int:
        session = self._sessions()
        try:
            stmt = select(func.count()).select_from(MemoryChunk)
            if memory_id is not None:
                stmt = stmt.where(MemoryChunk.memory_id == memory_id)
            return session.scalar(stmt) or 0
        except SQLAlchemyError as exc:
            raise StorageError("chunk count failed") from exc
        finally:
            session.close()
