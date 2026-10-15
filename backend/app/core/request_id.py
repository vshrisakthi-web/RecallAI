"""Request ID generation and validation (Module 3, Task 3.9).

A request ID lets a client correlate an error response with the request that
produced it. We accept a client-supplied ``X-Request-ID`` when it is safe, and
otherwise generate a random one. The value is exposed via a ContextVar (for
logging) and echoed in a response header.
"""

from __future__ import annotations

import re
import secrets
from contextvars import ContextVar
from typing import Optional

from app.core.config import settings

# The active request id for the current async context (available to logging).
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id_var", default=None)

# Safe charset: URL/identifier friendly. Prevents header injection, control
# characters, and unbounded values.
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def new_request_id() -> str:
    """Generate a short, unguessable request id."""
    return secrets.token_hex(8)


def is_valid_request_id(value: str) -> bool:
    """A client-provided id must be within the length limit and safe chars."""
    if not value:
        return False
    if len(value) > settings.max_request_id:
        return False
    return bool(_REQUEST_ID_RE.match(value))


def resolve_request_id(client_value: Optional[str]) -> tuple[str, bool]:
    """Return (request_id, ok). ok=False means the client value was present but
    unsafe (caller should reject the request)."""
    if client_value is None:
        return new_request_id(), True
    if is_valid_request_id(client_value):
        return client_value, True
    return new_request_id(), False


def set_request_id(value: str) -> None:
    request_id_var.set(value)


def get_request_id() -> Optional[str]:
    return request_id_var.get()
