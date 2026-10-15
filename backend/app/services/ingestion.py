"""Ingestion orchestration service (Module 3, Tasks 3.3, 3.5, 3.6).

Coordinates the pipeline for each source type:

    validated request schema
      -> normalize text (deterministic)
      -> compute content hash
      -> build a canonical record
      -> repository.save_or_get (dedup + persist)
      -> IngestionResult

The service holds no storage logic; it delegates persistence to the repository.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.validation import url_domain
from app.repositories.base import IngestionRepository
from app.schemas.browser import BrowserCaptureIn
from app.schemas.common import (
    CanonicalRecord,
    IngestionResult,
    ResultStatus,
    SourceType,
)
from app.schemas.note import NoteIn
from app.schemas.transcript import TranscriptIn
from app.services.hashing import content_hash, is_safe_id, new_id
from app.services.normalize import normalize_text


class IngestionService:
    def __init__(self, repo: IngestionRepository) -> None:
        self._repo = repo

    # --- Browser ----------------------------------------------------------

    def ingest_browser(self, payload: BrowserCaptureIn, request_id: str) -> IngestionResult:
        normalized = normalize_text(payload.extractedText)
        digest = content_hash(normalized)
        record_id = payload.id if (payload.id and is_safe_id(payload.id)) else new_id("mem")

        record = CanonicalRecord(
            id=record_id,
            source_type=SourceType.browser,
            title=payload.title,
            normalized_text=normalized,
            source_url=payload.url,
            domain=payload.domain,
            source_metadata={},
            captured_at=payload.capturedAt,  # already a UTC datetime (validated)
            ingested_at=_now(),
            content_hash=digest,
            request_id=request_id,
            capture_type=payload.captureType,
            selected_text=payload.selectedText,
            surrounding_context=payload.surroundingContext,
            extraction_status=payload.status,
            note=payload.note,
        )
        return self._finish(record)

    # --- Transcript -------------------------------------------------------

    def ingest_transcript(self, payload: TranscriptIn, request_id: str) -> IngestionResult:
        normalized = normalize_text(payload.transcript)
        digest = content_hash(normalized)

        metadata = dict(payload.metadata)
        if payload.source:
            metadata["source"] = payload.source

        domain = url_domain(payload.source_url) if payload.source_url else None

        record = CanonicalRecord(
            id=new_id("tr"),
            source_type=SourceType.transcript,
            title=payload.title,
            normalized_text=normalized,
            source_url=payload.source_url,
            domain=domain,
            source_metadata=metadata,
            captured_at=payload.captured_at or _now(),
            ingested_at=_now(),
            content_hash=digest,
            request_id=request_id,
        )
        return self._finish(record)

    # --- Note -------------------------------------------------------------

    def ingest_note(self, payload: NoteIn, request_id: str) -> IngestionResult:
        normalized = normalize_text(payload.note)
        digest = content_hash(normalized)

        metadata = dict(payload.metadata)
        if payload.tags:
            metadata["tags"] = payload.tags

        domain = url_domain(payload.source_url) if payload.source_url else None

        record = CanonicalRecord(
            id=new_id("note"),
            source_type=SourceType.note,
            title=payload.title,
            normalized_text=normalized,
            source_url=payload.source_url,
            domain=domain,
            source_metadata=metadata,
            captured_at=payload.captured_at or _now(),
            ingested_at=_now(),
            content_hash=digest,
            request_id=request_id,
        )
        return self._finish(record)

    # --- Shared -----------------------------------------------------------

    def _finish(self, record: CanonicalRecord) -> IngestionResult:
        stored, duplicate = self._repo.save_or_get(record)
        status = ResultStatus.duplicate if duplicate else ResultStatus.created
        message = (
            "An identical record already exists; returning the existing record."
            if duplicate
            else "Record accepted and stored."
        )
        return IngestionResult(
            duplicate=duplicate,
            status=status,
            message=message,
            record_id=stored.id,
            source_type=stored.source_type,
            content_hash=stored.content_hash,
            record=stored,
        )


def _now() -> datetime:
    return datetime.now(timezone.utc)
