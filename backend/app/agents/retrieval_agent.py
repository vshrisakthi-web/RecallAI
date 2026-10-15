"""Retrieval Agent for the agent harness (Module 8, Task 73).

Plain English: this stage gathers traceable evidence from actual RecallAI
memories. It calls the existing Module 6 hybrid retrieval service (keyword
+ semantic with RRF fusion), then trims the result to the harness policy
budgets: at most ``max_evidence_items`` passages totalling at most
``max_evidence_chars`` characters.

Design decisions (per the Task 73 plan):

* ``top_k`` bounds the service call, never ``limit``: ``retrieve()``
  validates ``limit`` but ignores it when assembling evidence, while
  ``top_k`` (falling back to ``rag_top_k``) actually stops the loop.
* Whole passages only: the char budget drops trailing items instead of
  slicing a passage mid-string, so excerpts stay verbatim.
* Deduplication by ``chunk_id``, keeping the first (highest fused score).
* Empty results are valid: ``state.evidence = []`` with an OK trace means
  "the records show nothing", never a failure (MISSING_EVIDENCE_RULE).
* Provenance is copied verbatim from ``Evidence``; missing metadata stays
  None. This stage never invents memory ids, chunk ids, or source URLs.
* Error mapping: ``RetrievalInputError`` becomes ``WorkflowRequestError``
  (permanent, never retried). ``StorageError`` and
  ``RetrievalUnavailableError`` record a safe error plus an ERROR trace,
  then propagate so the orchestrator can mark the run FAILED.
* This stage performs no LLM call and no durable write.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from app.agents.contracts import (
    Stage,
    Capability,
    require_capability,
    validate_stage_inputs,
    validate_stage_output,
)
from app.agents.resilience import call_with_retries
from app.agents.state import TraceStatus, WorkflowRequestError, WorkflowState
from app.repositories.base import StorageError
from app.services.evidence import RetrievalInputError, RetrievalUnavailableError

_UNAVAILABLE_MESSAGE = "Local retrieval is unavailable right now."


def _is_transient_retrieval_error(exc: BaseException) -> bool:
    """Only storage outages and retrieval-unavailable errors are retried.

    ``RetrievalInputError`` (bad input) and every contract error are
    permanent and never retried (Task 78).
    """
    return isinstance(exc, (RetrievalUnavailableError, StorageError))


def run_retrieval(
    state: WorkflowState,
    service,
    top_k: Optional[int] = None,
    clock: Optional[Callable[[], float]] = None,
) -> WorkflowState:
    """Run retrieval and store bounded evidence on ``state``.

    Args:
        state: the shared run; must carry ``user_query`` and an
            ``objective`` (set by the router) before this stage may run.
        service: a ``HybridRetrievalService`` (or test double) exposing
            ``retrieve(query, top_k=...)``.
        top_k: optional per-call cap; always clamped to
            ``policy.max_evidence_items`` so the policy stays authoritative.
        clock: optional monotonic clock for tests; defaults to
            ``time.perf_counter``.

    Raises:
        WorkflowRequestError: missing objective/query, or invalid input
            rejected by the service (permanent -- never retried).
        RetrievalUnavailableError / StorageError: outage; a safe error and
            an ERROR trace are recorded before propagating.
    """
    validate_stage_inputs(
        Stage.RETRIEVAL,
        {"user_query": state.user_query, "objective": state.objective},
    )
    require_capability(Stage.RETRIEVAL, Capability.SEARCH_MEMORIES)

    policy = state.policy
    if top_k is None:
        cap = policy.max_evidence_items
    else:
        cap = min(top_k, policy.max_evidence_items)
    if cap < 1:
        cap = 1

    now = clock or time.perf_counter
    started = now()
    result = call_with_retries(
        lambda: service.retrieve(state.user_query, top_k=cap),
        policy=policy,
        is_transient=_is_transient_retrieval_error,
    )
    if not result.ok:
        exc = result.error
        if isinstance(exc, RetrievalInputError):
            state.record_trace(
                stage=Stage.RETRIEVAL.value,
                status=TraceStatus.ERROR,
                duration_ms=_elapsed_ms(now, started),
                attempts=result.attempts,
                error_category="invalid_input",
            )
            raise WorkflowRequestError(str(exc)) from exc
        # Transient outage exhausted: safe error plus an ERROR trace, then
        # propagate so the orchestrator can mark the run FAILED.
        state.add_error(
            stage=Stage.RETRIEVAL.value,
            category="unavailable",
            message=_UNAVAILABLE_MESSAGE,
        )
        state.record_trace(
            stage=Stage.RETRIEVAL.value,
            status=TraceStatus.ERROR,
            duration_ms=_elapsed_ms(now, started),
            attempts=result.attempts,
            error_category="unavailable",
        )
        raise exc

    state.evidence = _apply_policy_bounds(list(result.value.evidence), policy)
    validate_stage_output(Stage.RETRIEVAL, ("evidence",))
    state.record_trace(
        stage=Stage.RETRIEVAL.value,
        status=TraceStatus.OK,
        duration_ms=_elapsed_ms(now, started),
        attempts=result.attempts,
    )
    return state


def _apply_policy_bounds(evidence: list, policy) -> list:
    """Deduplicate by chunk id, then enforce item and char budgets.

    Keeps whole passages only: items are accepted in ranked order while
    the running character total fits ``max_evidence_chars``; the first
    item is always kept (a single over-long passage is the service's
    verbatim excerpt, not ours to slice). Count never exceeds
    ``max_evidence_items``.
    """
    seen: set[str] = set()
    unique: list = []
    for item in evidence:
        if item is None:
            continue
        chunk_id = getattr(item, "chunk_id", None)
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        unique.append(item)

    bounded: list = []
    total_chars = 0
    for item in unique:
        if len(bounded) >= policy.max_evidence_items:
            break
        passage_len = len(getattr(item, "passage", "") or "")
        if bounded and total_chars + passage_len > policy.max_evidence_chars:
            break
        bounded.append(item)
        total_chars += passage_len
    return bounded


def _elapsed_ms(clock: Callable[[], float], started: float) -> int:
    """Milliseconds between ``started`` and now, never negative."""
    try:
        elapsed = clock() - started
    except Exception:
        return 0
    return max(0, int(elapsed * 1000))
