"""Workflow state model for the agent harness (Module 8, Task 71).

Plain English: one workflow run is one :class:`WorkflowState` — a single typed
record every stage reads from and writes to. Stages never chat with each
other; they communicate only through this shared state and the legal status
transitions below.

Decisions recorded here (design doc: ``docs/module-8-agent-harness.md``):

* Status and objective are closed enums. Illegal transitions raise
  :class:`InvalidTransitionError` instead of being ignored, so a failed stage
  can never quietly turn into a success.
* Errors and traces keep only safe fields (stage, category, message, duration,
  attempts) — never raw prompts, memory text, or secrets.
* ``run_id`` reuses ``app.services.hashing.new_id``: server-generated,
  unguessable, and valid under ``is_safe_id`` (so it is safe in URLs).
* State is transient while a run executes (Task 76). Persisting runs and
  approved tasks is a later, approval-gated concern (Task 79) and is
  deliberately absent here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Dict, FrozenSet, List, Optional

from app.agents.policies import HarnessPolicy
from app.services.hashing import new_id

Clock = Callable[[], datetime]

# Safe-message bounds: an error or clarification string never grows without
# limit, even when a model produced it.
_MAX_ERROR_MESSAGE_CHARS = 300
_MAX_CLARIFICATION_CHARS = 500


class RunStatus(str, Enum):
    """Lifecycle of one workflow run. A closed set — any other string is invalid."""

    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class Objective(str, Enum):
    """The only objectives the workflow understands (Task 72 routes to these)."""

    SEARCH = "search"
    SUMMARIZE = "summarize"
    ANALYZE_LEARNING = "analyze_learning"
    CREATE_TASKS = "create_tasks"


ALLOWED_OBJECTIVES: FrozenSet[str] = frozenset(objective.value for objective in Objective)


class TraceStatus(str, Enum):
    """Closed set of stage-trace outcomes."""

    OK = "ok"
    ERROR = "error"


TERMINAL_STATUSES: FrozenSet[RunStatus] = frozenset(
    {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.REJECTED, RunStatus.CANCELLED}
)

# The only legal status changes. Everything else raises instead of being
# ignored, so a failure can never silently become a success (or vice versa).
_ALLOWED_TRANSITIONS: Dict[RunStatus, FrozenSet[RunStatus]] = {
    RunStatus.PENDING: frozenset(
        {RunStatus.RUNNING, RunStatus.FAILED, RunStatus.CANCELLED}
    ),
    RunStatus.RUNNING: frozenset(
        {
            RunStatus.AWAITING_APPROVAL,
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.AWAITING_APPROVAL: frozenset(
        {RunStatus.COMPLETED, RunStatus.REJECTED, RunStatus.FAILED}
    ),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.REJECTED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
}


class WorkflowRequestError(ValueError):
    """Raised when a request or state change violates the harness contracts."""


class InvalidTransitionError(RuntimeError):
    """Raised when a status change is not in the allowed transition map."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _clip(message: str, limit: int) -> str:
    """Validate and bound a safe message so huge model output cannot land here."""
    if not isinstance(message, str) or not message.strip():
        raise WorkflowRequestError("A message must be non-empty text.")
    text = message.strip()
    if len(text) > limit:
        return text[:limit] + "..."
    return text


@dataclass(frozen=True)
class WorkflowError:
    """One safe, user-facing stage failure.

    ``category`` is a bounded failure label (validation, timeout,
    provider_unavailable, storage, contract, internal, ...) — never raw
    exception text, prompts, or memory content.
    """

    stage: str
    category: str
    message: str


@dataclass(frozen=True)
class StageTrace:
    """One stage execution record: sanitized, bounded, and human-readable."""

    stage: str
    status: TraceStatus
    duration_ms: int
    attempts: int = 1
    error_category: Optional[str] = None


@dataclass
class WorkflowState:
    """Typed shared state for one workflow run.

    ``evidence``, ``analysis``, and ``task_drafts`` hold validated stage
    outputs. They are typed loosely as objects until Task 77 introduces the
    shared Pydantic schemas; ``app.agents.contracts`` defines the structural
    contract each stage must satisfy when writing them.
    """

    run_id: str
    user_query: str
    policy: HarnessPolicy
    objective: Optional[Objective] = None
    status: RunStatus = RunStatus.PENDING
    errors: List[WorkflowError] = field(default_factory=list)
    evidence: List[object] = field(default_factory=list)
    analysis: Optional[object] = None
    task_drafts: List[object] = field(default_factory=list)
    trace: List[StageTrace] = field(default_factory=list)
    clarification: Optional[str] = None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls,
        user_query: str,
        policy: Optional[HarnessPolicy] = None,
        now: Optional[Clock] = None,
    ) -> "WorkflowState":
        """Validate the request and start a PENDING run with a fresh run_id."""
        policy = policy or HarnessPolicy.from_settings()
        clock = now or _utcnow
        if not isinstance(user_query, str) or not user_query.strip():
            raise WorkflowRequestError("A workflow run needs a non-empty question.")
        if len(user_query) > policy.max_query_chars:
            raise WorkflowRequestError(
                f"The question exceeds the {policy.max_query_chars}-character "
                "workflow limit."
            )
        stamp = clock()
        return cls(
            run_id=new_id("run"),
            user_query=user_query,
            policy=policy,
            created_at=stamp,
            updated_at=stamp,
        )

    # --- Status lifecycle ---------------------------------------------------

    def transition(self, to: RunStatus, now: Optional[Clock] = None) -> None:
        """Move to ``to`` or raise :class:`InvalidTransitionError`."""
        if not isinstance(to, RunStatus):
            raise InvalidTransitionError(
                f"{to!r} is not a valid run status."
            )
        if to not in _ALLOWED_TRANSITIONS[self.status]:
            raise InvalidTransitionError(
                f"A run cannot go from {self.status.value} to {to.value}."
            )
        self.status = to
        self.updated_at = (now or _utcnow)()

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    @property
    def requires_approval(self) -> bool:
        return self.status is RunStatus.AWAITING_APPROVAL

    # --- Objective and clarification ---------------------------------------

    def set_objective(
        self, objective: object, now: Optional[Clock] = None
    ) -> None:
        """Set a routing decision from the allowlist, or raise.

        Accepts an :class:`Objective` or its raw string value; anything else
        (including model output such as arbitrary tool names) is rejected
        before it can influence the pipeline. Setting an objective clears any
        earlier clarification.
        """
        if self.status not in (RunStatus.PENDING, RunStatus.RUNNING):
            raise WorkflowRequestError(
                "The objective can only be set while the run is starting or running."
            )
        if isinstance(objective, Objective):
            resolved = objective
        else:
            try:
                resolved = Objective(objective)
            except ValueError:
                shown = repr(objective)[:80]
                raise WorkflowRequestError(
                    f"Unsupported objective: {shown}. Allowed: "
                    + ", ".join(sorted(ALLOWED_OBJECTIVES))
                    + "."
                ) from None
        self.objective = resolved
        self.clarification = None
        self.updated_at = (now or _utcnow)()

    def set_clarification(
        self, message: str, now: Optional[Clock] = None
    ) -> None:
        """Record a safe clarification for an unsupported or ambiguous request.

        A clarification run never gets an objective: the orchestrator stops
        before retrieval so no stage acts on an unclear request.
        """
        if self.status not in (RunStatus.PENDING, RunStatus.RUNNING):
            raise WorkflowRequestError(
                "A clarification can only be set while the run is starting or running."
            )
        if self.objective is not None:
            raise WorkflowRequestError(
                "A clarification cannot be set after an objective was chosen."
            )
        self.clarification = _clip(message, _MAX_CLARIFICATION_CHARS)
        self.updated_at = (now or _utcnow)()

    # --- Errors and traces --------------------------------------------------

    def add_error(
        self,
        stage: str,
        category: str,
        message: str,
        now: Optional[Clock] = None,
    ) -> WorkflowError:
        """Record one safe user-facing error, bounded by ``max_errors``.

        When the cap is reached the OLDEST error is dropped, so the most
        recent failure is always visible. Per-stage detail lives in ``trace``;
        this list only feeds the user-facing response.
        """
        if not isinstance(stage, str) or not stage.strip():
            raise WorkflowRequestError("An error must name the stage it came from.")
        if not isinstance(category, str) or not category.strip():
            raise WorkflowRequestError("An error must carry a failure category.")
        error = WorkflowError(
            stage=stage.strip(),
            category=category.strip(),
            message=_clip(message, _MAX_ERROR_MESSAGE_CHARS),
        )
        self.errors.append(error)
        if len(self.errors) > self.policy.max_errors:
            del self.errors[0]
        self.updated_at = (now or _utcnow)()
        return error

    def record_trace(
        self,
        stage: str,
        status: TraceStatus,
        duration_ms: int,
        attempts: int = 1,
        error_category: Optional[str] = None,
        now: Optional[Clock] = None,
    ) -> StageTrace:
        """Append a sanitized stage record (stage, outcome, timing, attempts).

        Never pass prompt text, memory content, or exception detail here —
        only the bounded fields below. The list stays small by design: at
        most a handful of stages times ``policy.max_attempts``.
        """
        if not isinstance(stage, str) or not stage.strip():
            raise WorkflowRequestError("A trace must name the stage it records.")
        if not isinstance(status, TraceStatus):
            raise WorkflowRequestError("A trace status must be TraceStatus.OK or ERROR.")
        if not isinstance(duration_ms, int) or duration_ms < 0:
            raise WorkflowRequestError("A trace duration must be non-negative ms.")
        if not isinstance(attempts, int) or attempts < 1:
            raise WorkflowRequestError("A trace must record at least one attempt.")
        entry = StageTrace(
            stage=stage.strip(),
            status=status,
            duration_ms=duration_ms,
            attempts=attempts,
            error_category=(
                error_category.strip() if isinstance(error_category, str) else None
            ),
        )
        self.trace.append(entry)
        self.updated_at = (now or _utcnow)()
        return entry
