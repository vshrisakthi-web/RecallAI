"""Agent harness tests (Module 8, Task 71).

Covers the workflow state machine, harness policies, and stage contracts:
legal and illegal transitions, allowlisted objectives, bounded errors and
traces, policy limits with env overrides, capability enforcement, and the
evidence/approval rules the later agents depend on.

No database, network, or model is involved — the harness design is testable
in isolation, which is exactly the point of Task 71.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.agents.contracts import (
    APPROVAL_RULE,
    CONFLICTING_EVIDENCE_RULE,
    MISSING_EVIDENCE_RULE,
    PERSISTENCE_RULE,
    STAGE_CONTRACTS,
    UNSUPPORTED_CLAIM_RULE,
    Capability,
    CapabilityError,
    ContractError,
    Stage,
    UnknownEvidenceError,
    require_capability,
    validate_evidence_refs,
    validate_stage_inputs,
    validate_stage_output,
)
from app.agents.policies import HarnessPolicy
from app.agents.state import (
    ALLOWED_OBJECTIVES,
    TERMINAL_STATUSES,
    InvalidTransitionError,
    Objective,
    RunStatus,
    TraceStatus,
    WorkflowRequestError,
    WorkflowState,
)
from app.core.config import Settings
from app.services.hashing import is_safe_id

FIXED = datetime(2026, 10, 12, tzinfo=timezone.utc)


class Clock:
    """Deterministic clock: starts fixed, ticks only when told to."""

    def __init__(self) -> None:
        self.now = FIXED

    def __call__(self) -> datetime:
        return self.now

    def tick(self, seconds: int = 1) -> None:
        self.now = self.now + timedelta(seconds=seconds)


def make_policy(**overrides) -> HarnessPolicy:
    """Small, explicit policy so tests can probe every bound."""
    base = dict(
        max_query_chars=80,
        max_evidence_items=4,
        max_evidence_chars=400,
        max_tasks=3,
        max_task_title_chars=40,
        max_task_description_chars=120,
        stage_timeout_seconds=5,
        total_budget_seconds=20,
        max_attempts=2,
        max_errors=3,
    )
    base.update(overrides)
    return HarnessPolicy(**base)


def make_state(query="Review my RAG notes", policy=None, clock=None):
    clock = clock or Clock()
    return WorkflowState.create(query, policy or make_policy(), now=clock)


# --- WorkflowState: creation ------------------------------------------------


def test_create_assigns_unique_safe_run_ids():
    first = make_state()
    second = make_state()
    assert first.run_id != second.run_id
    assert first.run_id.startswith("run_")
    assert is_safe_id(first.run_id)
    assert len(first.run_id) <= 64


@pytest.mark.parametrize("query", ["", "   ", "\t\n"])
def test_create_rejects_empty_queries(query):
    with pytest.raises(WorkflowRequestError, match="non-empty"):
        make_state(query)


def test_create_rejects_oversized_query():
    with pytest.raises(WorkflowRequestError, match="exceeds"):
        make_state("x" * 81)


def test_new_run_is_pending_with_matching_timestamps():
    clock = Clock()
    state = make_state(clock=clock)
    assert state.status is RunStatus.PENDING
    assert state.created_at == FIXED
    assert state.updated_at == FIXED
    assert state.objective is None
    assert state.clarification is None
    clock.tick(5)
    state.transition(RunStatus.RUNNING, now=clock)
    assert state.updated_at > state.created_at


# --- Status transitions -----------------------------------------------------


def test_happy_path_transitions_to_awaiting_approval_then_rejected():
    clock = Clock()
    state = make_state(clock=clock)
    state.transition(RunStatus.RUNNING, now=clock)
    state.transition(RunStatus.AWAITING_APPROVAL, now=clock)
    assert state.requires_approval
    assert not state.is_terminal
    state.transition(RunStatus.REJECTED, now=clock)
    assert state.status is RunStatus.REJECTED
    assert state.is_terminal


def test_run_can_complete_without_approval_when_there_are_no_drafts():
    state = make_state()
    state.transition(RunStatus.RUNNING)
    state.transition(RunStatus.COMPLETED)
    assert state.is_terminal


def test_run_can_fail_from_pending_running_or_awaiting_approval():
    for start in (RunStatus.PENDING, RunStatus.RUNNING, RunStatus.AWAITING_APPROVAL):
        state = make_state()
        state.status = start
        state.transition(RunStatus.FAILED)
        assert state.status is RunStatus.FAILED


@pytest.mark.parametrize(
    "start,target",
    [
        (RunStatus.PENDING, RunStatus.COMPLETED),
        (RunStatus.PENDING, RunStatus.AWAITING_APPROVAL),
        (RunStatus.PENDING, RunStatus.REJECTED),
        (RunStatus.RUNNING, RunStatus.PENDING),
        (RunStatus.RUNNING, RunStatus.REJECTED),
        (RunStatus.AWAITING_APPROVAL, RunStatus.RUNNING),
        (RunStatus.AWAITING_APPROVAL, RunStatus.PENDING),
    ],
)
def test_illegal_transitions_raise_and_change_nothing(start, target):
    state = make_state()
    state.status = start
    with pytest.raises(InvalidTransitionError):
        state.transition(target)
    assert state.status is start


@pytest.mark.parametrize(
    "terminal", sorted(TERMINAL_STATUSES, key=lambda item: item.value)
)
def test_terminal_states_are_final(terminal):
    state = make_state()
    state.status = terminal
    for target in (
        RunStatus.PENDING,
        RunStatus.RUNNING,
        RunStatus.AWAITING_APPROVAL,
        RunStatus.COMPLETED,
    ):
        with pytest.raises(InvalidTransitionError):
            state.transition(target)


def test_transition_rejects_raw_strings():
    state = make_state()
    with pytest.raises(InvalidTransitionError, match="not a valid run status"):
        state.transition("completed")
