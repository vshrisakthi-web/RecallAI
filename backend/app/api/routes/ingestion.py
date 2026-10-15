"""Ingestion endpoints (Module 3, Tasks 3.3, 3.7, 3.8, 3.9).

Three source-specific endpoints share one pipeline and one response contract
(``IngestionResult``). HTTP status:
  - 201 Created   -> a new canonical record was stored
  - 200 OK        -> an identical record already existed (duplicate; idempotent)
  - 422           -> validation error (global handler in app.main)
  - 500           -> storage failure (global handler in app.main)

The repository dependency is requested only to ensure it is constructed/available
before the service runs; the service owns persistence.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import get_service
from app.core.request_id import get_request_id
from app.schemas.browser import BrowserCaptureIn
from app.schemas.common import IngestionResult
from app.schemas.note import NoteIn
from app.schemas.transcript import TranscriptIn
from app.services.ingestion import IngestionService

router = APIRouter(prefix="/ingest", tags=["ingestion"])


@router.post("/browser", response_model=IngestionResult, status_code=201)
def ingest_browser(
    payload: BrowserCaptureIn,
    response: Response,
    service: IngestionService = Depends(get_service),
) -> IngestionResult:
    result = service.ingest_browser(payload, get_request_id() or "")
    if result.duplicate:
        response.status_code = 200
    return result


@router.post("/transcript", response_model=IngestionResult, status_code=201)
def ingest_transcript(
    payload: TranscriptIn,
    response: Response,
    service: IngestionService = Depends(get_service),
) -> IngestionResult:
    result = service.ingest_transcript(payload, get_request_id() or "")
    if result.duplicate:
        response.status_code = 200
    return result


@router.post("/notes", response_model=IngestionResult, status_code=201)
def ingest_notes(
    payload: NoteIn,
    response: Response,
    service: IngestionService = Depends(get_service),
) -> IngestionResult:
    result = service.ingest_note(payload, get_request_id() or "")
    if result.duplicate:
        response.status_code = 200
    return result

