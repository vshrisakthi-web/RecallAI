"""SQLite source and memory repositories used by ingestion and read APIs."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy import Float, String, func, or_, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import Memory, Source
from app.repositories.base import IngestionRepository, StorageError
from app.schemas.common import CanonicalRecord
from app.services.hashing import content_hash, new_id


def _value(value):
    return value.value if hasattr(value, "value") else value


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _source_identity(record: CanonicalRecord) -> Optional[str]:
    if not record.source_url:
        return None
    source_type = _value(record.source_type)
    return content_hash(f"source\x00{source_type}\x00{record.source_url}")


def _dedup_key(record: CanonicalRecord) -> str:
    return "\x1f".join(
        [
            str(_value(record.source_type)),
            record.source_url or "",
            str(_value(record.capture_type) or ""),
            record.content_hash,
        ]
    )


def _record(memory: Memory, source: Source) -> CanonicalRecord:
    return CanonicalRecord(
        id=memory.id,
        source_type=source.source_type,
        source_id=source.id,
        title=memory.title,
        normalized_text=memory.normalized_content,
        source_url=source.canonical_source_url,
        domain=source.domain,
        source_metadata=memory.record_metadata or {},
        captured_at=_utc(memory.captured_at),
        ingested_at=_utc(memory.ingested_at),
        content_hash=memory.content_hash,
        request_id=memory.request_id,
        capture_type=memory.capture_type,
        selected_text=memory.selected_text,
        surrounding_context=memory.surrounding_context,
        extraction_status=memory.extraction_status,
        note=memory.note,
    )


class SourceRepository:
    """Source lookup and source creation within a caller-owned transaction."""

    def get_by_id(self, session: Session, source_id: str) -> Optional[Source]:
        return session.get(Source, source_id)

    def get_by_identity(self, session: Session, identity_key: str) -> Optional[Source]:
        return session.scalar(select(Source).where(Source.identity_key == identity_key))

    def create(self, session: Session, source: Source) -> Source:
        session.add(source)
        session.flush()
        return source


class MemoryRepository(IngestionRepository):
    """Transactional memory persistence, listing, search, and safe deletion."""

    def __init__(self, sessions: sessionmaker, sources: Optional[SourceRepository] = None):
        self._sessions = sessions
        self.sources = sources or SourceRepository()

    def save_or_get(self, record: CanonicalRecord) -> Tuple[CanonicalRecord, bool]:
        key = _dedup_key(record)
        session = self._sessions()
        try:
            existing = session.scalar(select(Memory).where(Memory.dedup_key == key))
            if existing is not None:
                return _record(existing, existing.source), True

            source = None
            identity = _source_identity(record)
            if identity:
                source = self.sources.get_by_identity(session, identity)
            if source is None:
                source = self.sources.create(
                    session,
                    Source(
                        id=new_id("src"),
                        identity_key=identity,
                        source_type=str(_value(record.source_type)),
                        canonical_source_url=record.source_url,
                        domain=record.domain,
                        title=record.title,
                        source_metadata=record.source_metadata,
                    ),
                )
            else:
                source.title = record.title
                source.domain = record.domain
                source.source_metadata = record.source_metadata

            record_id = record.id
            if session.get(Memory, record_id) is not None:
                record_id = new_id("mem")
            memory = Memory(
                id=record_id,
                source_id=source.id,
                title=record.title,
                normalized_content=record.normalized_text,
                content_hash=record.content_hash,
                dedup_key=key,
                captured_at=_utc(record.captured_at),
                ingested_at=_utc(record.ingested_at),
                request_id=record.request_id,
                capture_type=_value(record.capture_type),
                selected_text=record.selected_text,
                surrounding_context=record.surrounding_context,
                extraction_status=_value(record.extraction_status),
                note=record.note,
                record_metadata=record.source_metadata,
            )
            session.add(memory)
            session.commit()
            session.refresh(memory)
            return _record(memory, source), False
        except IntegrityError as exc:
            session.rollback()
            existing = session.scalar(select(Memory).where(Memory.dedup_key == key))
            if existing is not None:
                return _record(existing, existing.source), True
            raise StorageError("database uniqueness constraint rejected the record") from exc
        except SQLAlchemyError as exc:
            session.rollback()
            raise StorageError("database write failed") from exc
        finally:
            session.close()

    def get_by_id(self, record_id: str) -> Optional[CanonicalRecord]:
        session = self._sessions()
        try:
            memory = session.get(Memory, record_id)
            return _record(memory, memory.source) if memory is not None else None
        except SQLAlchemyError as exc:
            raise StorageError("database read failed") from exc
        finally:
            session.close()

    def list_recent(self, limit: int = 50) -> list[CanonicalRecord]:
        records, _ = self.list_memories(page=1, page_size=max(1, limit))
        return records[:max(0, limit)]

    def count(self) -> int:
        session = self._sessions()
        try:
            return session.scalar(select(func.count()).select_from(Memory)) or 0
        except SQLAlchemyError as exc:
            raise StorageError("database count failed") from exc
        finally:
            session.close()

    def list_memories(
        self,
        *,
        query: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        domain: Optional[str] = None,
        source_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 25,
    ) -> tuple[list[CanonicalRecord], int]:
        session = self._sessions()
        try:
            stmt = select(Memory, Source).join(Source, Memory.source_id == Source.id)
            conditions = []
            ranking = None

            if from_date is not None:
                start = datetime.combine(from_date, time.min, tzinfo=timezone.utc)
                conditions.append(Memory.captured_at >= start)
            if to_date is not None:
                end = datetime.combine(to_date, time.min, tzinfo=timezone.utc)
                conditions.append(Memory.captured_at < end + timedelta(days=1))
            if domain:
                conditions.append(Source.domain == domain)
            if source_type:
                conditions.append(Source.source_type == source_type)

            terms = re.findall(r"[\w]+", (query or ""), flags=re.UNICODE)
            if terms:
                fts_exists = session.scalar(
                    text("SELECT 1 FROM sqlite_master WHERE name = 'memories_fts'")
                )
                if fts_exists:
                    fts = text(
                        "SELECT memory_id, bm25(memories_fts) AS score "
                        "FROM memories_fts WHERE memories_fts MATCH :search_query"
                    ).columns(memory_id=String, score=Float).subquery("memory_search")
                    stmt = stmt.join(fts, fts.c.memory_id == Memory.id)
                    ranking = fts.c.score
                    stmt = stmt.params(search_query=" AND ".join(f'"{term}"' for term in terms))
                else:
                    for term in terms:
                        pattern = f"%{term}%"
                        conditions.append(
                            or_(
                                Memory.title.ilike(pattern, escape="\\"),
                                Memory.normalized_content.ilike(pattern, escape="\\"),
                                Source.title.ilike(pattern, escape="\\"),
                                Source.domain.ilike(pattern, escape="\\"),
                            )
                        )

            if conditions:
                stmt = stmt.where(*conditions)
            count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
            total = session.scalar(count_stmt) or 0
            if ranking is not None:
                stmt = stmt.order_by(ranking, Memory.captured_at.desc(), Memory.id.desc())
            else:
                stmt = stmt.order_by(Memory.captured_at.desc(), Memory.id.desc())
            rows = session.execute(stmt.offset((page - 1) * page_size).limit(page_size)).all()
            return [_record(memory, source) for memory, source in rows], total
        except SQLAlchemyError as exc:
            raise StorageError("database search failed") from exc
        finally:
            session.close()

    def delete_by_id(self, memory_id: str) -> bool:
        session = self._sessions()
        try:
            memory = session.get(Memory, memory_id)
            if memory is None:
                return False
            session.delete(memory)
            session.commit()
            return True
        except SQLAlchemyError as exc:
            session.rollback()
            raise StorageError("database delete failed") from exc
        finally:
            session.close()

    def get_source(self, source_id: str) -> Optional[dict]:
        session = self._sessions()
        try:
            source = self.sources.get_by_id(session, source_id)
            if source is None:
                return None
            return {
                "id": source.id,
                "source_type": source.source_type,
                "url": source.canonical_source_url,
                "domain": source.domain,
                "title": source.title,
                "metadata": source.source_metadata or {},
                "created_at": _utc(source.created_at),
                "updated_at": _utc(source.updated_at),
                "memory_count": session.scalar(
                    select(func.count()).select_from(Memory).where(Memory.source_id == source.id)
                ) or 0,
            }
        except SQLAlchemyError as exc:
            raise StorageError("database source lookup failed") from exc
        finally:
            session.close()
