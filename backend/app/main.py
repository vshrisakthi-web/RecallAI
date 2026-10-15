"""FastAPI application entrypoint (Module 3, Task 3.1, 3.9).

Wires middleware, routers (under ``/api/v1``), optional CORS, and consistent
exception handlers. Interactive docs are exposed at ``/docs`` (Swagger UI).

Run from the ``backend/`` directory:
    uvicorn app.main:app --reload
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import approval, health, ingestion, memories, retrieval, voice, workflow
from app.core.config import settings
from app.core.errors import error_response
from app.core.request_id import get_request_id, new_request_id
from app.middleware.request_id import RequestIdMiddleware
from app.repositories.base import StorageError

logger = logging.getLogger("recallai.ingestion")


def create_app() -> FastAPI:
    app = FastAPI(
        title="RecallAI Ingestion API",
        version="0.4.0",
        summary="Local ingestion, search, and structured memory API.",
        description=(
            "Privacy-first local ingestion service. It validates, normalizes, "
            "deduplicates, and stores submitted content in local SQLite. It never fetches URLs or "
            "calls external AI. Intended for local development; secure before any "
            "network exposure."
        ),
    )

    # Request-ID middleware must run first so every response carries an id.
    app.add_middleware(RequestIdMiddleware)

    # Optional, explicit CORS. Disabled unless RECALLAI_CORS_ORIGINS is set.
    if settings.cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_allow_origins),
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["*"],
        )

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(ingestion.router, prefix="/api/v1")
    app.include_router(memories.router, prefix="/api/v1")
    app.include_router(retrieval.router, prefix="/api/v1")
    app.include_router(workflow.router, prefix="/api/v1")
    app.include_router(approval.router, prefix="/api/v1")
    app.include_router(voice.router, prefix="/api/v1")

    _register_exception_handlers(app)
    return app


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", None) or get_request_id() or new_request_id()


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        # Flatten Pydantic errors into a safe, structured list (no stack traces).
        details = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err.get("loc", []) if p not in ("body",))
            details.append({"field": loc or "_", "issue": err.get("msg", "invalid"), "type": err.get("type", "")})
        return error_response(
            422, "VALIDATION_ERROR", "The submitted request is invalid.", _rid(request), details
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request: Request, exc: StarletteHTTPException):
        code = {
            404: "NOT_FOUND",
            422: "VALIDATION_ERROR",
            502: "PROVIDER_ERROR",
            503: "PROVIDER_NOT_CONFIGURED",
            504: "PROVIDER_TIMEOUT",
        }.get(exc.status_code, "HTTP_ERROR")
        details = [{"field": "_", "issue": str(exc.detail), "type": "http_error"}]
        return error_response(
            exc.status_code, code, str(exc.detail), _rid(request), details
        )

    @app.exception_handler(StorageError)
    async def storage_handler(request: Request, exc: StorageError):
        # Log the real cause server-side; return a safe message to the client.
        logger.exception("storage failure", extra={"request_id": _rid(request)})
        return error_response(
            500, "STORAGE_ERROR", "The record could not be stored.", _rid(request)
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        # Log full diagnostics; never leak internals to the client.
        logger.exception("unhandled error: %s", type(exc).__name__, extra={"request_id": _rid(request)})
        return error_response(
            500, "INTERNAL_ERROR", "An unexpected error occurred.", _rid(request)
        )


app = create_app()
