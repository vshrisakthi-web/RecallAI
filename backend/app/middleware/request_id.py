"""Request-ID middleware (Module 3, Task 3.9).

- Reads an optional ``X-Request-ID`` from the client.
- Rejects an unsafe/oversized client id with a 400 (never trusts it).
- Otherwise uses the client id, or generates a fresh one.
- Stores it on ``request.state`` (readable by handlers and error handlers) and
  echoes it back in the ``X-Request-ID`` response header.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.errors import error_response
from app.core.request_id import resolve_request_id, set_request_id


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        client_value = request.headers.get("x-request-id")
        request_id, ok = resolve_request_id(client_value)

        if not ok:
            # Client supplied an unsafe id: reject clearly (do not use it).
            return error_response(
                400,
                "INVALID_REQUEST_ID",
                "The provided X-Request-ID header is invalid (too long or contains "
                "unsupported characters).",
                request_id,
            )

        request.state.request_id = request_id
        set_request_id(request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
