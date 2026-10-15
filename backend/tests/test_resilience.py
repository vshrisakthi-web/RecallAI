"""Resilience tests for the agent harness (Module 8, Task 78).

Proves the behaviour the rest of the harness depends on:

* ``call_with_retries`` retries only transient failures, bounded by
  ``policy.max_attempts``; permanent failures return on the first attempt.
* The returned ``attempts`` is the true number of invocations, so a stage
  trace can report real retries (not a hardcoded 1).
* Exhausted transient failures still surface the final error and are never
  turned into a false success.
* ``run_with_timeout`` returns a fast value inline, and raises
  ``StageTimeoutError`` (never the value, never silently) when a stage
  overruns ``stage_timeout_seconds``.
* The three real stages (retrieval, analysis, task) all route their model /
  retrieval call through the helper and record the true attempt count.

No database, network, or model is required: the model boundary is a fake and
the clock/sleeper are injected, so retries are deterministic.
"""

from __future__ import annotations

import json
import time

import pytest

from app.agents.analysis_agent import (
    AnalysisModelUnavailableError,
    AnalysisResult,
    run_analysis,
)
from app.agents.policies import HarnessPolicy
from app.agents.resilience import (
    RetryResult,
    StageTimeoutError,
    call_with_retries,
    run_with_timeout,
)
from app.agents.state import Objective, TraceStatus, WorkflowState
from app.agents.task_agent import TaskModelUnavailableError, run_tasks
from app.services.evidence import Evidence


def make_policy(**overrides) -> HarnessPolicy:
    base = dict(
        max_query_chars=200,
        max_evidence_items=4,
        max_evidence_chars=2000,
        max_tasks=3,
        max_task_title_chars=40,
        max_task_description_chars=120,
        stage_timeout_seconds=5,
        total_budget_seconds=20,
        max_attempts=3,
        max_errors=5,
    )
    base.update(overrides)
    return HarnessPolicy(**base)


def make_evidence(chunk_id="c1", passage="RAG uses embeddings."):
    return Evidence(
        chunk_id=chunk_id, memory_id="m1", passage=passage,
        source_id=None, source_type="note", source_title="t",
        source_url=None, domain=None, captured_at=None,
        similarity=0.9, score=1.0,
    )


# --- call_with_retries: transient vs permanent classification -------------


def test_transient_failure_is_retried_until_success():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("temporary outage")
        return "ok"

    result = call_with_retries(
        flaky, policy=make_policy(max_attempts=3), is_transient=lambda exc: True,
    )
    assert result.ok is True
    assert result.value == "ok"
    assert result.attempts == 3
    assert calls["n"] == 3


def test_transient_exhaustion_returns_error_not_false_success():
    calls = {"n": 0}

    def always_down():
        calls["n"] += 1
        raise AnalysisModelUnavailableError("daemon down")

    result = call_with_retries(
        always_down,
        policy=make_policy(max_attempts=2),
        is_transient=lambda exc: isinstance(exc, AnalysisModelUnavailableError),
    )
    assert result.ok is False
    assert result.value is None
    assert isinstance(result.error, AnalysisModelUnavailableError)
    assert result.attempts == 2
    assert calls["n"] == 2


def test_permanent_failure_is_not_retried():
    calls = {"n": 0}

    def bad_json():
        calls["n"] += 1
        raise ValueError("permanent malformed output")

    result = call_with_retries(
        bad_json, policy=make_policy(max_attempts=5), is_transient=lambda exc: False,
    )
    assert result.ok is False
    assert isinstance(result.error, ValueError)
    # A permanent error returns on the FIRST attempt even with max_attempts=5.
    assert result.attempts == 1
    assert calls["n"] == 1


def test_sleeper_is_invoked_between_retries_only():
    slept: list[int] = []
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")
        return "done"

    result = call_with_retries(
        flaky, policy=make_policy(max_attempts=3), is_transient=lambda exc: True,
        sleeper=lambda attempt: slept.append(attempt),
    )
    assert result.ok is True
    assert result.attempts == 3
    # Two failures -> two sleeps (after attempt 1 and 2), none after success.
    assert slept == [1, 2]


def test_max_attempts_clamped_to_at_least_one():
    calls = {"n": 0}

    class _PolicyStub:
        # Bypasses HarnessPolicy validation to prove the helper is defensive
        # against a non-positive max_attempts (clamped to 1, not zero/loop).
        max_attempts = 0

    def always_down():
        calls["n"] += 1
        raise RuntimeError("down")

    result = call_with_retries(
        always_down, policy=_PolicyStub(), is_transient=lambda exc: True,
    )
    assert result.ok is False
    assert result.attempts == 1
    assert calls["n"] == 1


def test_retry_result_defaults_are_safe():
    empty = RetryResult()
    assert empty.value is None
    assert empty.attempts == 0
    assert empty.error is None
    assert empty.ok is True  # error is None


# --- run_with_timeout ------------------------------------------------------


def test_run_with_timeout_returns_fast_value():
    assert run_with_timeout(lambda: 42, timeout_seconds=5) == 42


def test_run_with_timeout_raises_on_overrun():
    def slow():
        time.sleep(1.0)
        return "never seen"

    with pytest.raises(StageTimeoutError):
        run_with_timeout(slow, timeout_seconds=0.05)


def test_run_with_timeout_nonpositive_runs_inline():
    # A non-positive budget means no extra bound: the operation runs and
    # returns its value (transport timeout remains the only guard).
    assert run_with_timeout(lambda: "inline", timeout_seconds=0) == "inline"


def test_run_with_timeout_invalid_budget_runs_inline():
    assert run_with_timeout(lambda: "ok", timeout_seconds="bad") == "ok"


# --- Real stages route through the helper and report true attempts --------


def _analysis_state(policy):
    state = WorkflowState.create("Review my notes", policy)
    state.set_objective(Objective.ANALYZE_LEARNING)
    state.evidence = [make_evidence("c1"), make_evidence("c2", "Vector notes.")]
    return state


def _analysis_reply():
    return json.dumps({
        "findings": [
            {"statement": "Notes cover RAG embeddings.", "evidence_refs": ["c1"]}
        ],
        "inferences": [],
        "unknowns": ["The records do not show exercises."],
        "conflicts": [],
    })


def _task_state(policy):
    state = WorkflowState.create("Draft next steps", policy)
    state.set_objective(Objective.CREATE_TASKS)
    state.evidence = [make_evidence("c1"), make_evidence("c2", "Vector notes.")]
    state.analysis = AnalysisResult.model_validate({
        "findings": [
            {"statement": "Notes cover RAG embeddings.", "evidence_refs": ["c1"]}
        ],
        "inferences": [],
        "unknowns": [],
        "conflicts": [],
    })
    return state


def _task_reply():
    return json.dumps({
        "tasks": [
            {"title": "Read embeddings guide",
             "description": "Study the retrieved guide.",
             "priority": "high", "source_ids": ["c1"],
             "kind": "outstanding", "status": "draft"},
        ]
    })


def test_analysis_retries_transient_outage_then_records_attempts():
    calls = {"n": 0}

    class FlakyModel:
        def analyze(self, prompt: str) -> str:
            calls["n"] += 1
            if calls["n"] < 2:
                raise AnalysisModelUnavailableError("temporary")
            return _analysis_reply()

    state = _analysis_state(make_policy(max_attempts=3))
    run_analysis(state, FlakyModel())
    assert calls["n"] == 2
    assert state.analysis is not None
    assert state.trace[-1].status is TraceStatus.OK
    # The OK trace must report the TRUE attempt count (a retry happened).
    assert state.trace[-1].attempts == 2


def test_analysis_exhausted_outage_records_true_attempts():
    class DownModel:
        def analyze(self, prompt: str) -> str:
            raise AnalysisModelUnavailableError("daemon down")

    state = _analysis_state(make_policy(max_attempts=2))
    with pytest.raises(AnalysisModelUnavailableError):
        run_analysis(state, DownModel())
    assert state.trace[-1].status is TraceStatus.ERROR
    assert state.trace[-1].attempts == 2


def test_task_agent_retries_then_records_true_attempts():
    calls = {"n": 0}

    class FlakyModel:
        def draft(self, prompt: str) -> str:
            calls["n"] += 1
            if calls["n"] < 3:
                raise TaskModelUnavailableError("temporary")
            return _task_reply()

    state = _task_state(make_policy(max_attempts=3))
    run_tasks(state, FlakyModel())
    assert calls["n"] == 3
    assert len(state.task_drafts) == 1
    assert state.trace[-1].status is TraceStatus.OK
    # Regression guard: this was hardcoded to 1 before the Task 78 fix.
    assert state.trace[-1].attempts == 3


def test_task_agent_exhausted_outage_records_true_attempts():
    class DownModel:
        def draft(self, prompt: str) -> str:
            raise TaskModelUnavailableError("daemon down")

    state = _task_state(make_policy(max_attempts=2))
    with pytest.raises(TaskModelUnavailableError):
        run_tasks(state, DownModel())
    assert state.trace[-1].status is TraceStatus.ERROR
    assert state.trace[-1].attempts == 2



# --- Orchestrator-level: retrieval retries and stage-timeout enforcement ---


class _AnalysisReply:
    def analyze(self, prompt: str) -> str:
        return _analysis_reply()


class _TaskReply:
    def draft(self, prompt: str) -> str:
        return _task_reply()


class _FakeRouter:
    def apply_to_state(self, state, user_query):
        state.set_objective(Objective.CREATE_TASKS)
        state.record_trace(stage="router", status=TraceStatus.OK,
                           duration_ms=0, attempts=1)
        return state


class _FakeRetrieval:
    """Retrieval double whose first ``fail_times`` calls fail transiently."""

    def __init__(self, fail_times=1):
        self.fail_times = fail_times
        self.calls = 0

    def retrieve(self, query, top_k=None):
        from app.services.evidence import (
            RetrievalResult,
            RetrievalUnavailableError,
        )
        from app.services.temporal import NormalizedQuery

        self.calls += 1
        if self.calls <= self.fail_times:
            raise RetrievalUnavailableError("embedding model down")
        return RetrievalResult(
            query=NormalizedQuery(original=query, text=query, temporal=None),
            evidence=[make_evidence("c1")],
            candidates_considered=1,
            temporal=None,
            channels=("keyword",),
        )


def _orchestrator(policy, retrieval):
    from app.agents.orchestrator import Orchestrator

    return Orchestrator(
        router=_FakeRouter(), retrieval=retrieval,
        analysis_model=_AnalysisReply(), task_model=_TaskReply(), policy=policy,
    )


def test_retrieval_retries_transient_then_completes():
    from app.agents.state import RunStatus

    orch = _orchestrator(make_policy(max_attempts=3), _FakeRetrieval(fail_times=2))
    state = orch.run("Draft next steps for RAG")
    assert state.status is RunStatus.AWAITING_APPROVAL
    assert orch.retrieval.calls == 3
    retrieval_trace = [t for t in state.trace if t.stage == "retrieval"][0]
    assert retrieval_trace.status is TraceStatus.OK
    assert retrieval_trace.attempts == 3


def test_retrieval_exhausted_marks_run_failed():
    from app.agents.state import RunStatus

    orch = _orchestrator(make_policy(max_attempts=2), _FakeRetrieval(fail_times=99))
    state = orch.run("Draft next steps for RAG")
    assert state.status is RunStatus.FAILED
    retrieval_trace = [t for t in state.trace if t.stage == "retrieval"][0]
    assert retrieval_trace.status is TraceStatus.ERROR
    assert retrieval_trace.attempts == 2
    # No false success: no drafts were produced and no later stage ran.
    assert state.task_drafts == []


class _SlowRouter:
    """Router double that sleeps past the per-stage timeout budget."""

    def __init__(self, sleep_seconds):
        self.sleep_seconds = sleep_seconds

    def apply_to_state(self, state, user_query):
        time.sleep(self.sleep_seconds)
        state.set_objective(Objective.SEARCH)
        state.record_trace(stage="router", status=TraceStatus.OK,
                           duration_ms=0, attempts=1)
        return state


def test_stage_over_timeout_marks_run_failed_not_hung():
    from app.agents.orchestrator import Orchestrator
    from app.agents.state import RunStatus

    orch = Orchestrator(
        router=_SlowRouter(sleep_seconds=1.5),
        retrieval=_FakeRetrieval(fail_times=0),
        analysis_model=_AnalysisReply(),
        task_model=_TaskReply(),
        policy=make_policy(stage_timeout_seconds=1, total_budget_seconds=20),
    )
    state = orch.run("Find my notes")
    assert state.status is RunStatus.FAILED
    assert any(e.category == "timeout" for e in state.errors)

