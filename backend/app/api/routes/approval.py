"""Approval endpoint for proposed agent task drafts (Module 8, Task 79).

``POST /api/v1/workflow/{run_id}/approve`` applies one explicit user decision
(``approve``, ``edit``, or ``reject``) to a run awaiting approval. It is the
only path that persists task drafts; the workflow endpoint and every agent
produce drafts but never write them.

Security posture:

* The decision is the only thing that authorizes a write. Model output,
  retrieved memories, or any generated text (including a claim that "the user
  approved") can never reach persistence — this endpoint never reads model
  text as authorization.
* Errors are mapped to safe, non-leaky responses: 404 unknown/stale run, 409
  wrong state or a replayed decision, 422 an invalid edit, 503 a storage
  failure (the run stays awaiting approval). No stack traces or memory content
  are ever returned.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from app.agents.approval import (
    ApprovalRequest,
    ApprovalValidationError,
    InvalidStateError,
    RunNotFoundError,
    apply_decision,
)
from app.agents.run_store import RunStore, get_default_run_store
from app.core.request_id import get_request_id
from app.repositories.base import StorageError
from app.services.task_service import TaskService

router = APIRouter(tags=["workflow"])
logger = logging.getLogger("recallai.approval")

# Bounds for the run id path segment (matches the workflow run_id format).
_MAX_RUN_ID_CHARS = 64


def get_task_service() -> TaskService:
    """Build the task service over the configured local SQLite database."""
    from app.database.session import get_session_local
    from app.repositories.task_repo import TaskRepository

    # A dedicated session factory for the tasks table; same DB/session config
    # as the rest of the app, reusing the existing session lifecycle.
    return TaskService(TaskRepository(get_session_local()))


def get_run_store() -> RunStore:
    """Return the process-wide run registry (overridable in tests)."""
    return get_default_run_store()


@router.post("/workflow/{run_id}/approve")
def approve_workflow(
    run_id: str,
    payload: ApprovalRequest,
    run_store: RunStore = Depends(get_run_store),
    task_service: TaskService = Depends(get_task_service),
):
    """Apply an explicit approval decision and (only then) persist drafts.

    Body: ``{"decision": "approve" | "edit" | "reject",
    "edited_drafts": {...}?}``. The body is a strict ``ApprovalRequest``
    (``extra="forbid"``): any unexpected field — including a model-style
    "approved": true claim — is rejected with 422 before any decision is read.
    Returns 200 with the run status and the ids of any persisted tasks. Maps
    unknown run to 404, invalid state/duplicate to 409, an invalid edit to
    422, and a storage failure to 503.
    """
    request_id = get_request_id()
    if not isinstance(run_id, str) or not run_id or len(run_id) > _MAX_RUN_ID_CHARS:
        raise HTTPException(status_code=404, detail="No workflow run matches that id.")

    edited_drafts = (
        payload.edited_drafts.model_dump(mode="json")
        if payload.edited_drafts is not None
        else None
    )

    try:
        return apply_decision(
            run_store,
            task_service,
            run_id,
            payload.decision.value,
            edited_drafts=edited_drafts,
        )
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ApprovalValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValidationError as exc:
        # A malformed edited_drafts structure that slipped past the body model.
        raise HTTPException(status_code=422, detail="The submitted edits are invalid.") from exc
    except StorageError as exc:
        logger.warning(
            "approval persistence failed (run id length=%d)",
            len(run_id),
            extra={"request_id": request_id},
        )
        raise HTTPException(
            status_code=503,
            detail="The approved tasks could not be saved right now.",
        ) from exc
