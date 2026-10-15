"""Workflow Orchestrator for the agent harness (Module 8, Task 76, Task 78).

Plain English: this is the conductor. Given one user question it runs the
router, then only the later stages the chosen objective requires — retrieval
for every objective, analysis for summarize / analyze_learning / create_tasks,
and task drafting only for create_tasks — then settles the run into a legal
terminal or approval status. It never persists anything: drafting is
in-memory, and durable writes are a separate approval-gated concern (Task 79).

Design decisions (design doc: ``docs/module-8-agent-harness.md``):

* The objective, not the model, decides the pipeline. SEARCH stops after
  retrieval; SUMMARIZE and ANALYZE_LEARNING stop after analysis; only
  CREATE_TASKS reaches the task stage, and only then can a run reach
  AWAITING_APPROVAL (and only if drafts were actually produced).
* A clarification stops the run before retrieval: no objective, so no stage
  acts on an unclear request, and the run completes with the clarification.
* Failures are reported, not hidden. A stage error marks the run FAILED with
  a safe, bounded error and keeps the traces already recorded; no later stage
  runs after a failure. Illegal status transitions can never turn a failure
  into a success.
* Retries and timeouts (Task 78) live inside the stage agents via
  ``app.agents.resilience.call_with_retries``; the orchestrator adds a
  coarse, run-level wall-clock budget guard so a long run cannot outlast
  ``policy.total_budget_seconds``.
* ``build_response`` produces a plain, JSON-serializable dict that matches the
  strict ``WorkflowResponse`` schema: enums as their ``.value`` strings, and
  server fields derived only from validated state — never raw model text or
  exception detail.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from app.agents.analysis_agent import run_analysis
from app.agents.policies import HarnessPolicy
from app.agents.resilience import StageTimeoutError, run_with_timeout
from app.agents.retrieval_agent import run_retrieval
from app.agents.state import (
    Objective,
    RunStatus,
    WorkflowRequestError,
    WorkflowState,
)
from app.agents.task_agent import run_tasks

# Objectives whose pipeline includes the analysis stage.
_ANALYSIS_OBJECTIVES = frozenset(
    {Objective.SUMMARIZE, Objective.ANALYZE_LEARNING, Objective.CREATE_TASKS}
)

_TIMEOUT_MESSAGE = "The request took too long to complete."
_STAGE_MESSAGE = "That step could not be completed just now."

class Orchestrator:
    """Runs one workflow end to end and returns the final :class:`WorkflowState`.

    Args:
        router: object exposing ``apply_to_state(state, user_query)`` (the
            :class:`QueryRouter` in production; a double in tests).
        retrieval: a ``HybridRetrievalService`` (or double) exposing
            ``retrieve(query, top_k=...)``.
        analysis_model: optional model boundary with ``analyze(prompt)``; when
            omitted the analysis agent builds its loopback Ollama default.
        task_model: optional model boundary with ``draft(prompt)``; likewise.
        policy: the :class:`HarnessPolicy`; defaults to application settings.
        clock: monotonic float clock (``time.perf_counter`` by default) used
            only for the coarse run-level budget guard; injectable in tests.
    """

    def __init__(
        self,
        router=None,
        retrieval=None,
        analysis_model=None,
        task_model=None,
        policy: Optional[HarnessPolicy] = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        # Local import keeps module import order flexible and avoids a cycle.
        from app.agents.routes.router import QueryRouter

        self.router = router or QueryRouter()
        self.retrieval = retrieval
        self.analysis_model = analysis_model
        self.task_model = task_model
        self.policy = policy or HarnessPolicy.from_settings()
        self._clock = clock or time.perf_counter
        self._budget_start: float = 0.0

    # --- Budget guard (Task 78) -------------------------------------------

    def _over_budget(self, state: WorkflowState) -> bool:
        """True when the run has exceeded its total wall-clock budget."""
        budget = getattr(state.policy, "total_budget_seconds", 0)
        try:
            budget = int(budget)
        except (TypeError, ValueError):
            return False
        if budget <= 0:
            return False
        return (self._clock() - self._budget_start) > budget

    # --- Failure handling (Task 78) ---------------------------------------

    def _fail(
        self,
        state: WorkflowState,
        stage: str,
        *,
        category: str = "internal",
        message: str = _STAGE_MESSAGE,
    ) -> None:
        """Settle a failed run: at most one safe error, then a legal FAILED move.

        Idempotent and safe: if the stage already recorded its own safe error
        (the agent stages do), none is added here; and if the run is already
        terminal nothing happens, so a second failure can never raise an
        illegal transition or erase the first recorded error.
        """
        if state.is_terminal:
            return
        already = any(e.stage == stage for e in state.errors)
        if not already:
            state.add_error(stage=stage, category=category, message=message)
        state.transition(RunStatus.FAILED)

    def _run_stage(
        self, state: WorkflowState, stage: str, func: Callable[[], None]
    ) -> bool:
        """Run one stage with a budget guard and safe failure handling.

        Returns True when the stage succeeded, or False when the run was
        marked FAILED (the caller must then stop). A ``WorkflowRequestError``
        is a request error, not a stage failure, so it propagates to the
        caller (the endpoint maps it to HTTP 422). A stage that overruns
        ``policy.stage_timeout_seconds`` is abandoned and marked FAILED with
        a timeout category (Task 78).
        """
        if self._over_budget(state):
            self._fail(state, stage, category="timeout", message=_TIMEOUT_MESSAGE)
            return False
        try:
            run_with_timeout(
                func, timeout_seconds=getattr(state.policy, "stage_timeout_seconds", 0)
            )
            return True
        except WorkflowRequestError:
            raise
        except StageTimeoutError:
            self._fail(state, stage, category="timeout", message=_TIMEOUT_MESSAGE)
            return False
        except Exception:
            self._fail(state, stage)
            return False

    def _settle(self, state: WorkflowState, awaiting: bool) -> None:
        """Move a fully successful run to its legal resting status.

        CREATE_TASKS rests in AWAITING_APPROVAL only when drafts exist; every
        other objective (and an empty CREATE_TASKS result) rests in COMPLETED.
        Called only after all required stages succeeded, so the run is still
        RUNNING and the transition is always legal.
        """
        state.transition(
            RunStatus.AWAITING_APPROVAL if awaiting else RunStatus.COMPLETED
        )

    def run(self, user_query: str) -> WorkflowState:
        """Run the whole workflow for one question and return the final state.

        Stages run strictly in the order the chosen objective requires; the
        first failure stops the run and marks it FAILED (a prior stage's
        traces are preserved). A clarification or a bad request short-circuits
        before retrieval.

        Raises:
            WorkflowRequestError: an empty/oversized question, or a stage that
                rejected the request as invalid input. The API layer maps this
                to HTTP 422; every other failure is reported as a FAILED run.
        """
        # Validates the question (empty/oversized) and starts a PENDING run;
        # raises WorkflowRequestError before any state or stage exists.
        state = WorkflowState.create(user_query, self.policy)
        state.transition(RunStatus.RUNNING)
        self._budget_start = self._clock()

        # 1. Route. A failure here fails the run; a clarification stops it.
        if not self._run_stage(
            state, "router", lambda: self.router.apply_to_state(state, user_query)
        ):
            return state
        if state.clarification is not None:
            self._settle(state, awaiting=False)
            return state

        # 2. Retrieve (every objective that reached here retrieves).
        if not self._run_stage(
            state, "retrieval", lambda: run_retrieval(state, self.retrieval)
        ):
            return state

        # 3. Analyze (summarize / analyze_learning / create_tasks only).
        if state.objective in _ANALYSIS_OBJECTIVES:
            if not self._run_stage(
                state, "analysis", lambda: run_analysis(state, self.analysis_model)
            ):
                return state

        # 4. Draft tasks (create_tasks only). Drafts stay in memory; they are
        #    never persisted by the orchestrator.
        if state.objective is Objective.CREATE_TASKS:
            if not self._run_stage(
                state, "task", lambda: run_tasks(state, self.task_model)
            ):
                return state
            self._settle(state, awaiting=bool(state.task_drafts))
            return state

        # search / summarize / analyze_learning all rest here.
        self._settle(state, awaiting=False)
        return state


def _objective_value(state: WorkflowState) -> Optional[str]:
    """Objective as its ``.value`` string (or None), never ``str(enum)``."""
    objective = state.objective
    if objective is None:
        return None
    return objective.value if hasattr(objective, "value") else str(objective)


def _trace_item(t) -> dict:
    """One trace record with the status enum serialized as its ``.value``."""
    status = t.status
    return {
        "stage": t.stage,
        "status": status.value if hasattr(status, "value") else str(status),
        "duration_ms": t.duration_ms,
        "attempts": t.attempts,
        "error_category": t.error_category,
    }


def _evidence_item(item) -> dict:
    """One evidence passage: only the response-schema fields, verbatim."""
    return {
        "chunk_id": item.chunk_id,
        "memory_id": item.memory_id,
        "source_title": getattr(item, "source_title", None),
        "source_url": getattr(item, "source_url", None),
        "passage": item.passage,
    }


def _draft_item(d) -> dict:
    """One task draft as a plain dict (JSON-safe, enum values as strings)."""
    if hasattr(d, "model_dump"):
        return d.model_dump(mode="json")
    return {
        "title": d.title,
        "description": d.description,
        "priority": getattr(d.priority, "value", d.priority),
        "source_ids": list(d.source_ids),
        "kind": getattr(d.kind, "value", d.kind),
        "status": getattr(d, "status", "draft"),
    }


def build_response(state: WorkflowState) -> dict:
    """Build the JSON-serializable workflow response from ``state``.

    Mirrors the ``WorkflowResponse`` schema exactly: enums (``objective``,
    ``status``, trace ``status``) serialize as their ``.value`` strings, not
    ``str(enum)``. Findings come from the validated analysis result; every
    item derives from validated state, so no raw model text, prompt, or
    exception detail can reach the response.
    """
    analysis = state.analysis
    findings = []
    if analysis is not None:
        for f in getattr(analysis, "findings", None) or []:
            findings.append(
                {
                    "statement": f.statement,
                    "evidence_refs": list(f.evidence_refs),
                }
            )
    return {
        "run_id": state.run_id,
        "objective": _objective_value(state),
        "status": state.status.value if hasattr(state.status, "value") else str(state.status),
        "clarification": state.clarification,
        "findings": findings,
        "evidence": [_evidence_item(e) for e in state.evidence],
        "task_drafts": [_draft_item(d) for d in state.task_drafts],
        "errors": [
            {"stage": e.stage, "category": e.category, "message": e.message}
            for e in state.errors
        ],
        "trace": [_trace_item(t) for t in state.trace],
    }

