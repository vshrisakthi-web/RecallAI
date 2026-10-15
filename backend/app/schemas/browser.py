"""Browser capture ingestion request (Module 3, Tasks 3.2, 3.4).

Field names intentionally mirror the extension's ``CaptureRecord`` (camelCase,
see ``extension/types/index.ts``) so the Module 2 backend adapter can POST a
record directly without a translation layer. The extension's ``id`` is optional
here: if absent or unsafe the server generates one. ``contentLength`` is accepted
but ignored — the server always recomputes it from the normalized text.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.config import settings
from app.core.validation import (
    parse_timestamp_utc,
    validate_domain_matches,
    validate_http_url,
)
from app.schemas.common import CaptureType, ExtractionStatus


class BrowserCaptureIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Optional[str] = None
    title: str
    url: str
    domain: str
    capturedAt: str = Field(description="ISO 8601 timestamp (UTC, e.g. trailing 'Z').")
    captureType: CaptureType
    extractedText: str
    selectedText: Optional[str] = None
    surroundingContext: Optional[str] = None
    status: Optional[ExtractionStatus] = ExtractionStatus.ok
    # Accepted for compatibility; recomputed server-side (not trusted).
    contentLength: Optional[int] = None
    note: Optional[str] = None

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        return validate_http_url(v)

    @field_validator("domain")
    @classmethod
    def _domain_matches_url(cls, v: str, info) -> str:
        url = info.data.get("url")
        if url:
            return validate_domain_matches(v, url)
        return v.strip().lower()

    @field_validator("capturedAt")
    @classmethod
    def _timestamp(cls, v: str):
        return parse_timestamp_utc(v)

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("title must not be empty")
        if len(stripped) > settings.max_title:
            raise ValueError(f"title exceeds maximum length of {settings.max_title} characters")
        return stripped

    @field_validator("extractedText")
    @classmethod
    def _text(cls, v: str) -> str:
        if v is None or not v.strip():
            raise ValueError("extractedText must not be empty or whitespace-only")
        if len(v) > settings.max_browser_text:
            raise ValueError(
                f"extractedText exceeds maximum length of {settings.max_browser_text} characters"
            )
        return v

    @field_validator("selectedText")
    @classmethod
    def _selected(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if len(v) > settings.max_selection_text:
            raise ValueError(
                f"selectedText exceeds maximum length of {settings.max_selection_text} characters"
            )
        return v

    @field_validator("surroundingContext")
    @classmethod
    def _context(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if len(v) > settings.max_context_text:
            raise ValueError(
                f"surroundingContext exceeds maximum length of {settings.max_context_text} characters"
            )
        return v

    @model_validator(mode="after")
    def _selection_requires_text(self) -> "BrowserCaptureIn":
        if self.captureType == CaptureType.selection:
            if not (self.selectedText and self.selectedText.strip()):
                raise ValueError("a selection capture requires non-empty selectedText")
        return self
