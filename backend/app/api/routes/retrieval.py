"""Retrieval endpoint for the Ask RecallAI surface (Module 6, Task 6.6).

``POST /api/v1/ask`` answers a question with **grounded evidence** from locally
stored memories. It deliberately does not generate prose: returning an invented
answer would let the UI present a guess as fact. The client decides how to
present evidence, and the response says plainly how strong that evidence is.

Privacy posture, matching the rest of this backend:

* No credentials are accepted (there is no ``api_key`` field) and none are sent
  — the embedding model is local and loopback-only.
* The question is never logged. Only its length and outcome are, so logs cannot
  become a leak of personal memory content.
* Deleted memories cannot appear: cascade deletion removes their chunks and
  vectors, and evidence assembly requires the memory row to exist.
* Provider and database failures map onto the shared error envelope and never
  leak internals.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_indexing_service, get_repository, get_retrieval_service
from app.core.config import settings
from app.core.request_id import get_request_id
from app.repositories.sqlite_store import MemoryRepository
from app.schemas.retrieval import AskRequest, AskResponse, EvidenceItem
from app.services.evidence import RetrievalInputError, RetrievalUnavailableError
from app.services.hybrid import HybridRetrievalService
from app.services.indexing import IndexingService, IndexingUnavailableError
from app.services.prompt import assess_confidence

router = APIRouter(tags=["retrieval"])
logger = logging.getLogger("recallai.retrieval")


@router.post("/ask", response_model=AskResponse)
def ask(request: AskRequest, service: HybridRetrievalService = Depends(get_retrieval_service)):
    """Retrieve grounded evidence for a question from local memories.

    Returns 200 with an empty ``evidence`` list when nothing matched — that is a
    successful search that found nothing, which is different from a failure.
    """
    request_id = get_request_id()

    try:
        result = service.retrieve(
            request.question,
            top_k=request.top_k,
            from_date=request.from_date,
            to_date=request.to_date,
        )
    except RetrievalInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RetrievalUnavailableError:
        logger.warning(
            "retrieval unavailable (question length=%d)",
            len(request.question),
            extra={"request_id": request_id},
        )
        raise HTTPException(
            status_code=503,
            detail="Local retrieval is unavailable. Is the embedding model running?",
        ) from None

    confidence = assess_confidence(result.evidence, settings)
    temporal = result.temporal

    items = [
        EvidenceItem(
            chunk_id=item.chunk_id,
            memory_id=item.memory_id,
            source_id=item.source_id,
            source_type=item.source_type,
            source_title=item.source_title,
            source_url=item.source_url,
            domain=item.domain,
            captured_at=item.captured_at,
            passage=item.passage,
            similarity=item.similarity,
            keyword_rank=item.keyword_rank,
            score=item.score,
            matched_by=list(item.matched_by),
            confidence=confidence.level,
        )
        for item in result.evidence
    ]

    # Only the outcome is logged — never the question text or any passage.
    logger.info(
        "retrieval completed (question length=%d, evidence=%d, confidence=%s, channels=%s)",
        len(request.question),
        len(items),
        confidence.level,
        ",".join(result.channels),
        extra={"request_id": request_id},
    )

    return AskResponse(
        question=result.query.original,
        evidence=items,
        confidence=confidence.level,
        channels=list(result.channels),
        candidates_considered=result.candidates_considered,
        temporal_expression=temporal.expression if temporal else None,
        temporal_from=temporal.from_date if temporal else None,
        temporal_to=temporal.to_date if temporal else None,
        request_id=request_id,
    )


@router.post("/memories/{memory_id}/index")
def index_memory(
    memory_id: str,
    repository: MemoryRepository = Depends(get_repository),
    indexer: IndexingService = Depends(get_indexing_service),
):
    """Build the retrieval index for one stored memory (Tasks 6.1-6.3).

    Indexing is explicit and user-initiated, never automatic: it needs the local
    embedding model, and saving a memory must not depend on that model being
    installed. A 404 means the memory does not exist; a 503 means the model is
    unavailable and nothing was indexed.
    """
    if repository.get_by_id(memory_id) is None:
        raise HTTPException(status_code=404, detail="Memory not found")

    try:
        outcome = indexer.index_memory(memory_id)
    except IndexingUnavailableError:
        raise HTTPException(
            status_code=503,
            detail="The local embedding model is unavailable on this server.",
        ) from None

    return {
        "memory_id": outcome.memory_id,
        "status": outcome.status,
        "chunk_count": outcome.chunk_count,
        "detail": outcome.detail,
        "request_id": get_request_id(),
    }


@router.post("/index")
def index_pending(
    limit: int = 100,
    indexer: IndexingService = Depends(get_indexing_service),
):
    """Index every memory that has chunks but no vector yet.

    This is how an existing database is brought up to date after the embedding
    model is installed. It is idempotent: unchanged content produces the same
    stable chunk ids and replaces rows rather than duplicating them.
    """
    outcomes = indexer.index_pending_memories(limit=limit)
    return {
        "indexed": sum(1 for o in outcomes if o.indexed),
        "skipped": sum(1 for o in outcomes if not o.indexed),
        "results": [
            {
                "memory_id": o.memory_id,
                "status": o.status,
                "chunk_count": o.chunk_count,
                "detail": o.detail,
            }
            for o in outcomes
        ],
        "request_id": get_request_id(),
    }

