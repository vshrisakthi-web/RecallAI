"""Transcript import request (Module 3, Tasks 3.2, 3.4, 3.7).

Accepts transcript text supplied by a user or another legitimate source. It does
NOT fetch transcripts from any provider — the backend only processes submitted
content.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import settings
from app.core.validation import parse_timestamp_utc, validate_http_url, validate_metadata


class TranscriptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    transcript: str = Field(description="The transcript text.")
    source_url: Optional[str] = Field(default=None, description="Optional origin URL (http/https).")
    source: Optional[str] = Field(default=None, description="Where the transcript came from.")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    captured_at: Optional[str] = Field(
        default=None,
        description="Optional ISO 8601 timestamp (UTC). Defaults to ingestion time if omitted.",
    )

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("title must not be empty")
        if len(stripped) > settings.max_title:
            raise ValueError(f"title exceeds maximum length of {settings.max_title} characters")
        return stripped

    @field_validator("transcript")
    @classmethod
    def _text(cls, v: str) -> str:
        if v is None or not v.strip():
            raise ValueError("transcript text must not be empty or whitespace-only")
        if len(v) > settings.max_transcript_text:
            raise ValueError(
                f"transcript exceeds maximum length of {settings.max_transcript_text} characters"
            )
        return v

    @field_validator("source_url")
    @classmethod
    def _url(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        return validate_http_url(v)

    @field_validator("captured_at")
    @classmethod
    def _timestamp(cls, v: Optional[str]):
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return parse_timestamp_utc(v)

    @field_validator("metadata")
    @classmethod
    def _metadata(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        return validate_metadata(v)

    @field_validator("source")
    @classmethod
    def _source(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        stripped = v.strip()
        if len(stripped) > settings.max_title:
            raise ValueError("source exceeds maximum length")
        return stripped or None
