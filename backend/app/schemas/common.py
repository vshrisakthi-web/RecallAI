"""Shared enums, the canonical ingestion record, and response envelopes.

The canonical record is the single internal representation that every source
type (browser, transcript, note) is normalized into. Response envelopes describe
what the API returns for created/duplicate results; error responses use the
separate envelope in ``app.core.errors``.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class SourceType(str, Enum):
    browser = "browser"
    transcript = "transcript"
    note = "note"


class CaptureType(str, Enum):
    """Mirrors the extension's captureType."""
    full_page = "full-page"
    selection = "selection"


class ExtractionStatus(str, Enum):
    """Mirrors the extension's ExtractionStatus (kept verbatim from Module 2)."""
    ok = "ok"
    empty = "empty"
    partial = "partial"
    unsupported = "unsupported"
    error = "error"


class ResultStatus(str, Enum):
    """Outcome of an ingestion attempt."""
    created = "created"
    duplicate = "duplicate"


# --- Canonical record ------------------------------------------------------


class CanonicalRecord(BaseModel):
    """The stored, source-agnostic representation of an ingested item.

    Snake_case on purpose: this is a new server-side contract. It preserves the
    browser capture's important fields (selected text, surrounding context,
    status, note) so nothing is silently discarded.
    """

    model_config = ConfigDict(use_enum_values=True)

    id: str = Field(description="Stable record id (client id when safe, else generated).")
    source_type: SourceType
    source_id: Optional[str] = Field(default=None, description="Persisted source record id, when available.")
    title: str
    normalized_text: str = Field(description="Deterministically normalized primary text.")
    source_url: Optional[str] = Field(default=None, description="Original URL, when applicable.")
    domain: Optional[str] = Field(default=None, description="Verified domain from source_url.")
    source_metadata: Dict[str, Any] = Field(default_factory=dict, description="Bounded source metadata.")
    captured_at: datetime = Field(description="Source event time, normalized to UTC.")
    ingested_at: datetime = Field(description="Server ingestion time (UTC).")
    content_hash: str = Field(description="sha256 of normalized_text.")
    request_id: str = Field(description="Request id / trace reference.")

    # Browser-specific preserved fields (None for transcript/note).
    capture_type: Optional[CaptureType] = None
    selected_text: Optional[str] = None
    surrounding_context: Optional[str] = None
    extraction_status: Optional[ExtractionStatus] = None
    note: Optional[str] = None


# --- Response envelopes ----------------------------------------------------


class IngestionResult(BaseModel):
    """Successful (created or duplicate) ingestion response."""

    duplicate: bool
    status: ResultStatus
    message: str
    record_id: str
    source_type: SourceType
    content_hash: str
    record: CanonicalRecord


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.4.0"
