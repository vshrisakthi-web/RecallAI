"""Manual notes import request (Module 3, Tasks 3.2, 3.4, 3.8).

Notes written or pasted by the user. A URL is optional and only relevant when
the note references a source. Optional tags are stored in metadata.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import settings
from app.core.validation import parse_timestamp_utc, validate_http_url, validate_metadata


class NoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    note: str = Field(description="The note text.")
    source_url: Optional[str] = Field(default=None, description="Optional reference URL (http/https).")
    tags: List[str] = Field(default_factory=list)
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

    @field_validator("note")
    @classmethod
    def _text(cls, v: str) -> str:
        if v is None or not v.strip():
            raise ValueError("note text must not be empty or whitespace-only")
        if len(v) > settings.max_note_text:
            raise ValueError(
                f"note exceeds maximum length of {settings.max_note_text} characters"
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

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: List[str]) -> List[str]:
        if len(v) > settings.max_metadata_items:
            raise ValueError(f"a note may have at most {settings.max_metadata_items} tags")
        cleaned: List[str] = []
        for tag in v:
            if not isinstance(tag, str):
                raise ValueError("each tag must be a string")
            t = tag.strip()
            if not t:
                raise ValueError("tags must not be empty")
            if len(t) > settings.max_metadata_value:
                raise ValueError(
                    f"each tag must be <= {settings.max_metadata_value} characters"
                )
            cleaned.append(t)
        return cleaned
