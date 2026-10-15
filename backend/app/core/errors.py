"""Error envelope helpers (Module 3, Task 3.9).

Every error uses one shape:
    {"error": {"code": ..., "message": ..., "details": [...], "request_id": ...}}

Success responses for ingestion use a separate, documented shape (see
``app.schemas``); errors always use this envelope so clients have one contract.
"""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse


def error_body(code: str, message: str, details: list, request_id: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details, "request_id": request_id}}


def error_response(
    status_code: int, code: str, message: str, request_id: str, details: list | None = None
) -> JSONResponse:
    body = error_body(code, message, details or [], request_id)
    return JSONResponse(status_code=status_code, content=body, headers={"X-Request-ID": request_id})
