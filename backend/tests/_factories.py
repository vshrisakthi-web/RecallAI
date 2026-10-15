"""Shared test factories (Module 3, Task 3.10)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.schemas.common import CanonicalRecord, SourceType
from app.services.hashing import content_hash
from app.services.normalize import normalize_text


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def browser_payload(**overrides):
    """A valid browser capture payload (mirrors the extension CaptureRecord)."""
    payload = {
        "id": "mem_test1",
        "title": "Understanding Vector Databases",
        "url": "https://techblog.example/vector-db",
        "domain": "techblog.example",
        "capturedAt": iso(utcnow() - timedelta(minutes=5)),
        "captureType": "full-page",
        "extractedText": "Vector databases store embeddings and enable fast similarity search.",
        "status": "ok",
        "contentLength": 67,
    }
    payload.update(overrides)
    return payload


def transcript_payload(**overrides):
    payload = {
        "title": "Podcast Episode 12 — Local AI",
        "transcript": (
            "Host: Welcome back. Today we discuss running language models locally.\n\n"
            "Guest: The key advantage is privacy; your data never leaves the device."
        ),
        "source_url": "https://podcast.example/ep12",
        "source": "podcast.example",
        "metadata": {"duration_seconds": 1820, "language": "en"},
    }
    payload.update(overrides)
    return payload


def note_payload(**overrides):
    payload = {
        "title": "Reading list",
        "note": "Remember to read the HNSW paper and compare it against IVF indexing.",
        "tags": ["reading", "vector-search"],
        "metadata": {"priority": "high"},
    }
    payload.update(overrides)
    return payload


def make_record(**overrides) -> CanonicalRecord:
    """A valid canonical record for repository unit tests."""
    text = overrides.pop("_text", "some normalized body text")
    base = {
        "id": "ing_test",
        "source_type": SourceType.note,
        "title": "A note",
        "normalized_text": text,
        "source_url": None,
        "domain": None,
        "source_metadata": {},
        "captured_at": utcnow(),
        "ingested_at": utcnow(),
        "content_hash": content_hash(normalize_text(text)),
        "request_id": "req_test",
    }
    base.update(overrides)
    return CanonicalRecord(**base)
