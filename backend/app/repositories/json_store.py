"""JSON-file-backed ingestion repository (Module 3, Task 3.13).

A small, deterministic, dev-friendly store that PERSISTS ACROSS RESTARTS (unlike
an in-memory dict). Records live in a single JSON file (``{"records": [...]}``).
It is intentionally simple and can be swapped for SQLite/Postgres later without
touching routes or services — they only see ``IngestionRepository``.

Deduplication: a record is considered a duplicate when another record with the
same dedup key (source type + source url + capture type + content hash) already
exists. See ``dedup_key_of``. Identical retries therefore never create a second
record (idempotent).

Concurrency: a process-wide lock makes read-modify-write atomic within a single
process/worker. This is NOT safe across multiple OS processes (e.g. several
uvicorn workers); a real database with a unique constraint is required for that
(see docs).
"""

from __future__ import annotations

import json
import os
import threading
from typing import List, Optional, Tuple

from app.repositories.base import IngestionRepository, StorageError
from app.schemas.common import CanonicalRecord


def dedup_key_of(record: CanonicalRecord) -> str:
    """Recompute a record's dedup key from its canonical fields.

    Includes capture_type so a full-page and a selection capture of the same URL
    are distinct, and never includes the title so distinct notes/articles with a
    similar title are not merged.
    """
    return "\x1f".join(
        [
            str(record.source_type),
            record.source_url or "",
            (record.capture_type or ""),
            record.content_hash,
        ]
    )


class JsonFileRepository(IngestionRepository):
    def __init__(self, path: str) -> None:
        self._path = os.path.abspath(path)
        self._lock = threading.Lock()
        self._ensure_parent_dir()

    # -- public API --------------------------------------------------------

    def save_or_get(self, record: CanonicalRecord) -> Tuple[CanonicalRecord, bool]:
        with self._lock:
            records = self._load()
            key = dedup_key_of(record)

            for existing in records:
                if dedup_key_of(existing) == key:
                    return existing, True

            # Ensure id uniqueness: if the (possibly client-supplied) id collides
            # with a different-content record, mint a fresh one rather than
            # clobbering. Imported here to avoid a cycle at module load.
            from app.services.hashing import new_id

            if any(r.id == record.id for r in records):
                record = record.model_copy(update={"id": new_id()})

            records.append(record)
            self._persist(records)
            return record, False

    def get_by_id(self, record_id: str) -> Optional[CanonicalRecord]:
        with self._lock:
            for r in self._load():
                if r.id == record_id:
                    return r
            return None

    def list_recent(self, limit: int = 50) -> List[CanonicalRecord]:
        with self._lock:
            records = self._load()
        records = sorted(records, key=lambda r: r.ingested_at, reverse=True)
        return records[: max(0, limit)]

    def count(self) -> int:
        with self._lock:
            return len(self._load())

    # -- internals ---------------------------------------------------------

    def _ensure_parent_dir(self) -> None:
        parent = os.path.dirname(self._path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    def _load(self) -> List[CanonicalRecord]:
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except FileNotFoundError:
            return []
        except (json.JSONDecodeError, OSError) as exc:
            raise StorageError(f"failed to read storage file: {exc}") from exc

        items = raw.get("records", []) if isinstance(raw, dict) else []
        out: List[CanonicalRecord] = []
        for item in items:
            try:
                out.append(CanonicalRecord.model_validate(item))
            except Exception:
                # Skip corrupt entries rather than failing the whole store.
                continue
        return out

    def _persist(self, records: List[CanonicalRecord]) -> None:
        payload = {"records": [r.model_dump(mode="json") for r in records]}
        tmp = self._path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False)
            os.replace(tmp, self._path)
        except OSError as exc:
            raise StorageError(f"failed to write storage file: {exc}") from exc
