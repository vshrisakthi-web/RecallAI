"""List, search, inspect, and delete locally stored memories."""

from __future__ import annotations

import ipaddress
import math
import re
from datetime import date
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_repository, get_summarization_service
from app.core.config import OllamaConfigError
from app.core.request_id import get_request_id
from app.repositories.sqlite_store import MemoryRepository
from app.schemas.common import SourceType
from app.schemas.memory import MemoryDetailResponse, MemoryListResponse, SourceResponse
from app.schemas.summarization import MemorySummaryResponse
from app.services.summarization import (
    OllamaSummarizationService,
    SummaryInputError,
    SummaryModelUnavailableError,
    SummaryResponseError,
)

router = APIRouter(tags=["memories"])
_DOMAIN_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def _domain(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip().lower().rstrip(".")
    if not normalized:
        raise HTTPException(status_code=422, detail="domain must not be empty")
    try:
        ipaddress.ip_address(normalized)
        return normalized
    except ValueError:
        if len(normalized) > 253 or not all(
            _DOMAIN_LABEL.fullmatch(label) for label in normalized.split(".")
        ):
            raise HTTPException(status_code=422, detail="domain must be a hostname")
        return normalized


@router.get("/memories", response_model=MemoryListResponse)
def list_memories(
    q: Optional[str] = Query(default=None, max_length=256),
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    domain: Optional[str] = Query(default=None, max_length=253),
    source_type: Optional[SourceType] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    repository: MemoryRepository = Depends(get_repository),
) -> MemoryListResponse:
    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=422, detail="from_date must not be after to_date")
    normalized_domain = _domain(domain)
    items, total = repository.list_memories(
        query=q,
        from_date=from_date,
        to_date=to_date,
        domain=normalized_domain,
        source_type=source_type.value if source_type else None,
        page=page,
        page_size=page_size,
    )
    return MemoryListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=math.ceil(total / page_size) if total else 0,
    )


@router.get("/memories/{memory_id}", response_model=MemoryDetailResponse)
def get_memory(
    memory_id: str,
    repository: MemoryRepository = Depends(get_repository),
) -> MemoryDetailResponse:
    memory = repository.get_by_id(memory_id)
    if memory is None or memory.source_id is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    source = repository.get_source(memory.source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Memory source not found")
    return MemoryDetailResponse(memory=memory, source=SourceResponse(**source))


@router.post("/memories/{memory_id}/summary", response_model=MemorySummaryResponse)
def summarize_memory(
    memory_id: str,
    repository: MemoryRepository = Depends(get_repository),
    summarizer: OllamaSummarizationService = Depends(get_summarization_service),
) -> MemorySummaryResponse:
    """Summarize one stored memory with a local Ollama model (Task 5.6).

    Only the memory's normalized text is handed to the summarization service —
    never URLs, titles, metadata, other memories, or credentials. The request
    targets a loopback-only local model (no cloud service), and provider and
    configuration failures are mapped onto the shared error envelope.
    """
    memory = repository.get_by_id(memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")

    source_text = memory.normalized_text
    if not source_text.strip():
        raise HTTPException(
            status_code=422,
            detail="This memory has no text to summarize.",
        )

    try:
        result = summarizer.summarize(source_text)
    except SummaryInputError as exc:
        # e.g. stored text exceeds the configured provider input limit.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (OllamaConfigError, SummaryModelUnavailableError):
        # Non-loopback/misconfigured endpoint, Ollama daemon not running, or
        # the configured model has not been pulled.
        raise HTTPException(
            status_code=503,
            detail="The local summarization model is unavailable on this server.",
        ) from None
    except SummaryResponseError:
        raise HTTPException(
            status_code=502,
            detail="The summarization provider returned an unusable response.",
        ) from None
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="The summarization provider timed out.",
        ) from None
    except httpx.HTTPError:
        raise HTTPException(
            status_code=502,
            detail="The summarization provider could not be reached.",
        ) from None

    return MemorySummaryResponse(
        memory_id=memory_id,
        summary=result.summary,
        model=result.model,
    )


@router.delete("/memories/{memory_id}")
def delete_memory(
    memory_id: str,
    repository: MemoryRepository = Depends(get_repository),
) -> dict[str, object]:
    if not repository.delete_by_id(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"deleted": True, "id": memory_id, "request_id": get_request_id()}


@router.get("/sources/{source_id}", response_model=SourceResponse)
def get_source(
    source_id: str,
    repository: MemoryRepository = Depends(get_repository),
) -> SourceResponse:
    source = repository.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return SourceResponse(**source)
