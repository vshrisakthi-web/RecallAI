"""Pure validation helpers shared by the Pydantic schemas (Module 3, Task 3.4).

These functions raise ``ValueError`` with clear, user-facing messages so Pydantic
turns them into structured 422 validation errors. They never perform network
I/O — the backend only inspects submitted content, it does not fetch URLs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from urllib.parse import urlsplit

from app.core.config import settings


def validate_http_url(value: str) -> str:
    """Require a well-formed http(s) URL. Returns the trimmed URL.

    Rejects other schemes (javascript:, data:, file:, ftp:...) and malformed
    input. Enforces the configured max length.
    """
    if value is None:
        raise ValueError("url is required")
    trimmed = value.strip()
    if not trimmed:
        raise ValueError("url must not be empty")
    if len(trimmed) > settings.max_url:
        raise ValueError(f"url exceeds maximum length of {settings.max_url} characters")
    parts = urlsplit(trimmed)
    if parts.scheme not in ("http", "https"):
        raise ValueError("url must use the http or https scheme")
    if not parts.netloc or not parts.hostname:
        raise ValueError("url must include a valid host")
    return trimmed


def url_domain(value: str) -> str:
    """Extract the hostname (no port) from a validated http(s) URL."""
    return (urlsplit(value).hostname or "").lower()


def validate_domain_matches(domain: str, url: str) -> str:
    """Verify a caller-supplied domain matches the parsed URL host.

    We never trust a caller-supplied domain on its own; it must agree with the
    URL. Comparison is case-insensitive and ignores an optional port.
    """
    expected = url_domain(url)
    provided = (domain or "").strip().lower()
    if not provided:
        raise ValueError("domain is required for browser captures")
    if provided != expected:
        raise ValueError(
            f"domain '{domain}' does not match the host '{expected}' parsed from the url"
        )
    return provided


def parse_timestamp_utc(value: Any) -> datetime:
    """Parse an ISO 8601 timestamp to a timezone-aware UTC datetime.

    - Accepts a trailing ``Z``.
    - Requires an explicit timezone (naive timestamps are rejected, since the
      extension always sends UTC with ``Z`` — see Module 3 docs).
    - Rejects malformed input rather than substituting 'now'.
    - Rejects values outside a documented sanity range.
    """
    if isinstance(value, datetime):
        dt = value
    else:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("timestamp must be a non-empty ISO 8601 string")
        text = value.strip()
        # datetime.fromisoformat on 3.9/3.10 does not accept a trailing 'Z'.
        if text.endswith("Z") or text.endswith("z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            raise ValueError("timestamp must be a valid ISO 8601 date-time")

    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("timestamp must include an explicit timezone (e.g. 'Z' or an offset)")

    dt_utc = dt.astimezone(timezone.utc)

    if dt_utc.year < settings.min_year:
        raise ValueError(f"timestamp year must not be earlier than {settings.min_year}")

    now = datetime.now(timezone.utc)
    if dt_utc > now + timedelta(minutes=settings.max_future_skew_minutes):
        raise ValueError(
            "timestamp is too far in the future "
            f"(allowed skew: {settings.max_future_skew_minutes} minutes)"
        )
    return dt_utc


def validate_metadata(value: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a bounded, shallow metadata object.

    Prevents unbounded/deeply nested objects (a simple DoS / abuse guard):
    - at most ``max_metadata_items`` keys,
    - scalar values only (str/int/float/bool/None), strings bounded in length,
    - depth limited to a flat mapping of scalars.
    """
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("metadata must be an object")
    if len(value) > settings.max_metadata_items:
        raise ValueError(
            f"metadata may contain at most {settings.max_metadata_items} keys"
        )
    for key, val in value.items():
        if not isinstance(key, str) or len(key) > settings.max_metadata_value:
            raise ValueError("metadata keys must be strings within the length limit")
        _validate_scalar(val)
    return value


def _validate_scalar(val: Any) -> None:
    if val is None or isinstance(val, (int, float, bool)):
        return
    if isinstance(val, str):
        if len(val) > settings.max_metadata_value:
            raise ValueError(
                f"metadata string values must be <= {settings.max_metadata_value} characters"
            )
        return
    if isinstance(val, dict):
        if len(val) > settings.max_metadata_items:
            raise ValueError("nested metadata objects are too large")
        for k, v in val.items():
            if not isinstance(k, str):
                raise ValueError("nested metadata keys must be strings")
            _validate_scalar(v)
        return
    if isinstance(val, (list, tuple)):
        if len(val) > settings.max_metadata_items:
            raise ValueError("metadata lists are too large")
        for item in val:
            _validate_scalar(item)
        return
    raise ValueError("metadata values must be scalars, lists, or shallow objects")
