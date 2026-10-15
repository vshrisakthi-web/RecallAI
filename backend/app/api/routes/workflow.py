"""Workflow endpoint for the agent harness (Module 8, Task 76).

``POST /api/v1/workflow`` runs one orchestrated workflow — router,
retrieval, analysis, task drafting as the objective requires — and
returns the structured result. It persists nothing: drafts stay drafts
until the Task 79 approval endpoint, and no workflow rows are stored.

Privacy posture, matching the rest of this backend:

* No credentials are accepted and none are sent — all models are local
  and loopback-only.
* The question is never logged. Only its length and outcome are.
* Model outages map onto the shared error envelope and never leak
  internals.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError

from app.agents.orchestrator import build_response
from app.agents.run_store import RunStore, get_default_run_store
from app.agents.schemas import WorkflowResponse, validate_workflow_response
from app.api.deps import get_orchestrator
from app.agents.state import RunStatus, WorkflowRequestError
from app.core.request_id import get_request_id

router = APIRouter(tags=["workflow"])
logger = logging.getLogger("recallai.workflow")


class WorkflowRunRequest(BaseModel):
    """One workflow request: a question, nothing else (no credentials)."""

    question: str = Field(min_length=1, max_length=1000)


def get_run_store() -> RunStore:
    """Return the process-wide run registry (overridable in tests)."""
    return get_default_run_store()


@router.post("/workflow", response_model=WorkflowResponse)
def run_workflow(
    request: WorkflowRunRequest,
    orchestrator=Depends(get_orchestrator),
    run_store: RunStore = Depends(get_run_store),
):
    """Run the orchestrated workflow and return its structured result.

    Returns 200 with the validated run result (including clarification
    and FAILED runs — a failed stage is reported, not hidden). Raises
    422 for an invalid question and 503 when a local model or index is
    unavailable. A 500 is returned only if the orchestrator produced a
    response that fails response validation (never malformed data).

    A run that settles in ``AWAITING_APPROVAL`` (proposed task drafts) is
    registered in the in-process run store so the approval endpoint can act
    on it. Nothing is persisted here — drafts stay drafts until an explicit
    approval. Other runs (completed, failed, clarification) are not stored.
    """
    request_id = get_request_id()
    try:
        state = orchestrator.run(request.question)
    except WorkflowRequestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (RuntimeError, ValueError) as exc:
        logger.warning(
            "workflow unavailable (question length=%d)",
            len(request.question),
            extra={"request_id": request_id},
        )
        raise HTTPException(
            status_code=503,
            detail="Local workflow is unavailable. Is the embedding model running?",
        ) from exc

    # Register only runs awaiting approval; put() ignores any other status.
    if state.status is RunStatus.AWAITING_APPROVAL:
        run_store.put(state)

    try:
        return validate_workflow_response(build_response(state))
    except ValidationError:
        logger.warning(
            "workflow response failed validation (question length=%d)",
            len(request.question),
            extra={"request_id": request_id},
        )
        raise HTTPException(
            status_code=500,
            detail="The workflow produced an invalid response.",
        ) from None
