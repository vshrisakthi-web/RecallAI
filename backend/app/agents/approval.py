"""Human approval for proposed task drafts (Module 8, Task 79).

Plain English: this is the security boundary. An LLM can *propose* task
drafts, but nothing is persisted until a real, explicit application-level
decision reaches :func:`apply_decision` through the approval endpoint. Model
output, retrieved memories, or any generated text — including a string that
claims "the user approved" — can never authorize a write; only a submitted
``decision`` of ``approve``/``edit``/``reject`` can.

What this module guarantees:

* The run must exist and be in ``AWAITING_APPROVAL`` (else ``RunNotFoundError``
  or ``InvalidStateError``).
* ``approve`` persists the drafts already on the run; ``edit`` re-validates the
  submitted drafts with the *same* rules (strict schema, task-count cap,
  title/description caps, and every ``source_id`` present in the run's
  retrieved evidence) and persists only those; ``reject`` persists nothing.
* A persistence failure (``StorageError``) propagates and the run stays in
  ``AWAITING_APPROVAL`` — a run is marked ``COMPLETED`` only after the durable
  write succeeds.
* The decision is recorded in the run's trace; terminal transitions use the
  legal state machine (``AWAITING_APPROVAL -> COMPLETED`` / ``REJECTED``).
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, ValidationError

from app.agents.contracts import (
    Stage,
    UnknownEvidenceError,
    validate_evidence_refs,
)
from app.agents.run_store import RunStore
from app.agents.state import RunStatus, TraceStatus, WorkflowState
from app.agents.task_agent import TaskDraft, TaskDraftList
from app.repositories.base import StorageError
from app.services.task_service import TaskService


class ApprovalDecision(str, Enum):
    """The only decisions a user may submit."""

    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"


class ApprovalRequest(BaseModel):
    """A single approval submission: exactly one decision, plus edits.

    Strict (``extra="forbid"``): an unexpected field — including anything that
    looks like a model's "approved" note — is rejected outright.
    """

    model_config = ConfigDict(extra="forbid")

    decision: ApprovalDecision
    edited_drafts: Optional[TaskDraftList] = None


class ApprovalError(RuntimeError):
    """Base class for approval failures mapped to safe HTTP responses."""


class RunNotFoundError(ApprovalError):
    """The run id is unknown or was never awaiting approval (-> 404)."""


class InvalidStateError(ApprovalError):
    """The run is not awaiting approval (wrong state or already decided) (-> 409)."""


class ApprovalValidationError(ApprovalError):
    """The submitted edit failed validation (bad schema/refs/caps) (-> 422)."""


def _validate_edited_drafts(edited: TaskDraftList, run: WorkflowState) -> List[TaskDraft]:
    """Validate submitted edited drafts against the run's evidence and policy."""
    policy = run.policy
    count_cap = getattr(policy, "max_tasks", len(edited.tasks) or 1)
    title_cap = getattr(policy, "max_task_title_chars", None)
    desc_cap = getattr(policy, "max_task_description_chars", None)

    if len(edited.tasks) > count_cap:
        raise ApprovalValidationError(
            f"An edit may not exceed the {count_cap}-task limit."
        )

    available = [getattr(item, "chunk_id", "") for item in run.evidence]
    claimed: List[str] = []
    for draft in edited.tasks:
        claimed.extend(draft.source_ids)
    try:
        validate_evidence_refs(claimed, available)
    except UnknownEvidenceError as exc:
        raise ApprovalValidationError(str(exc)) from exc

    for draft in edited.tasks:
        if title_cap is not None and len(draft.title) > title_cap:
            raise ApprovalValidationError("An edited task title is too long.")
        if desc_cap is not None and len(draft.description) > desc_cap:
            raise ApprovalValidationError("An edited task description is too long.")
    return list(edited.tasks)


def _record_decision(run: WorkflowState, decision: ApprovalDecision, *, persisted: bool) -> None:
    """Append a sanitized decision record to the run trace (no memory text)."""
    category = f"decision_{decision.value}"
    run.record_trace(
        stage=Stage.APPROVAL.value,
        status=TraceStatus.OK,
        duration_ms=0,
        attempts=1,
        error_category=None if persisted else category,
    )


def apply_decision(
    run_store: RunStore,
    task_service: TaskService,
    run_id: str,
    decision: str,
    edited_drafts: Optional[dict] = None,
) -> dict:
    """Apply an explicit user decision to a run awaiting approval.

    Args:
        run_store: the in-process registry holding the ``AWAITING_APPROVAL``
            run.
        task_service: the sole durable task-write path.
        run_id: the run to decide on.
        decision: ``"approve"``, ``"edit"``, or ``"reject"``.
        edited_drafts: for ``edit``, the submitted draft list (a
            ``TaskDraftList``-shaped dict). Ignored for ``approve``/``reject``.

    Returns:
        ``{"run_id": ..., "status": ..., "persisted_task_ids": [...]}`` with
        ``status`` being ``"completed"`` (approve/edit) or ``"rejected"``.

    Raises:
        RunNotFoundError: unknown or expired run id.
        InvalidStateError: run is not in ``AWAITING_APPROVAL``.
        ApprovalValidationError: an edit failed validation.
        StorageError: persistence failed (run stays ``AWAITING_APPROVAL``).
    """
    try:
        parsed_decision = ApprovalDecision(decision)
    except ValueError as exc:
        raise ApprovalValidationError(
            "The decision must be approve, edit, or reject."
        ) from exc

    run = run_store.get(run_id)
    if run is None:
        raise RunNotFoundError("No workflow run is awaiting approval for that id.")

    if run.status is not RunStatus.AWAITING_APPROVAL:
        raise InvalidStateError("This workflow run is no longer awaiting approval.")

    if parsed_decision is ApprovalDecision.REJECT:
        run.transition(RunStatus.REJECTED)
        _record_decision(run, ApprovalDecision.REJECT, persisted=False)
        run_store.remove(run.run_id)
        return {
            "run_id": run.run_id,
            "status": run.status.value,
            "persisted_task_ids": [],
        }

    if parsed_decision is ApprovalDecision.APPROVE:
        drafts = list(run.task_drafts)
    else:  # EDIT — re-validate the submitted drafts with the same rules.
        if edited_drafts is None:
            raise ApprovalValidationError("An edit decision requires edited drafts.")
        try:
            edited = TaskDraftList.model_validate(edited_drafts)
        except ValidationError as exc:
            raise ApprovalValidationError("The submitted edits are invalid.") from exc
        drafts = _validate_edited_drafts(edited, run)

    # Serialize only after validation; model_dump(mode="json") keeps enums as
    # their string values so the JSON column is clean and stable.
    payload = [d.model_dump(mode="json") for d in drafts]

    # Durable write. On failure this raises StorageError and the run is left in
    # AWAITING_APPROVAL — never marked completed on a failed/partial write.
    persisted_ids = task_service.persist_drafts(payload, run.run_id)

    run.transition(RunStatus.COMPLETED)
    _record_decision(run, ApprovalDecision.APPROVE, persisted=True)
    run_store.remove(run.run_id)
    return {
        "run_id": run.run_id,
        "status": run.status.value,
        "persisted_task_ids": persisted_ids,
    }

