"""Content hashing and stable id helpers (Module 3, Task 3.6)."""

from __future__ import annotations

import hashlib
import re
import secrets

# A safe client-supplied id: alphanumerics, dash, underscore, dot; bounded.
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def content_hash(normalized_text: str) -> str:
    """Stable sha256 hex digest of normalized text."""
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


def is_safe_id(value: str) -> bool:
    return bool(value) and bool(_SAFE_ID.match(value))


def new_id(prefix: str = "ing") -> str:
    """Generate a server-side unique id (url-safe, unguessable)."""
    return f"{prefix}_{secrets.token_hex(12)}"
