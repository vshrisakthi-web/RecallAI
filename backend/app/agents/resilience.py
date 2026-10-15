"""Bounded retries for transient agent failures (Module 8, Task 78).

Plain English: some failures are worth trying again — a momentary loss of
the local Ollama server, a storage hiccup, an embedding-model timeout.
Others are permanent and must never be retried: bad user input, schema
violations, fabricated evidence references, or contract/permission errors.
This module holds one generic, framework-free retry loop and nothing else.

Design decisions:

* It is intentionally free of imports from the agent modules, so the
  agents can import it without a circular dependency. Each agent supplies
  its own ``is_transient`` predicate — it knows which of *its* exceptions
  are transient.
* ``call_with_retries`` never raises: it returns a :class:`RetryResult`
  carrying the value on success, or the final error plus the true attempt
  count. The caller decides how to record the trace (so ``attempts`` is
  accurate) and how to re-raise, preserving each agent's existing error
  semantics.
* Retries are bounded by ``policy.max_attempts``. There is no unbounded
  loop and no background work: a synchronous call that cannot be
  interrupted is bounded by the client-level timeout the transport
  already carries (see ``ollama_timeout_seconds`` and the retrieval
  service timeout), and the run-level wall-clock budget is enforced
  between stages by the orchestrator.
* Backoff is injectable and defaults to no delay. For a local loopback
  service an immediate, bounded retry is appropriate and keeps tests
  deterministic; a real backoff sleeper can be passed where wanted.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Any, Callable, Optional

# The default backoff: do nothing between attempts. Bounded (zero) and
# safe for tests. Production agents may pass a real, capped sleeper.
_NO_DELAY: Callable[[int], None] = lambda _attempt: None


@dataclass
class RetryResult:
    """Outcome of a retried operation.

    Attributes:
        value: the operation's return value on success, else ``None``.
        attempts: how many times the operation was actually invoked
            (always >= 1). This is the number the caller records in the
            stage trace so retries are visible without extra traces.
        error: the final exception if every attempt failed (or the first
            non-transient exception), else ``None``.
    """

    value: Any = None
    attempts: int = 0
    error: Optional[BaseException] = None

    @property
    def ok(self) -> bool:
        return self.error is None


def call_with_retries(
    operation: Callable[[], Any],
    *,
    policy: Any,
    is_transient: Callable[[BaseException], bool],
    sleeper: Callable[[int], None] = _NO_DELAY,
) -> RetryResult:
    """Run ``operation``, retrying only failures ``is_transient`` accepts.

    Args:
        operation: a zero-argument callable performing the external call.
        policy: the run policy; ``policy.max_attempts`` bounds the tries
            (clamped to at least 1).
        is_transient: predicate returning True only for failures that are
            safe and plausibly worth retrying. A permanent failure returns
            immediately on the first attempt — never retried.
        sleeper: called with the upcoming attempt number before a retry;
            defaults to no delay. Inject a recording fake in tests.

    Returns:
        A :class:`RetryResult`. On success ``value`` is set and ``error``
        is ``None``; on failure ``error`` holds the final exception and
        ``attempts`` reflects how many tries were made.
    """
    try:
        max_attempts = int(getattr(policy, "max_attempts", 1))
    except (TypeError, ValueError):
        max_attempts = 1
    if max_attempts < 1:
        max_attempts = 1

    attempts = 0
    while True:
        attempts += 1
        try:
            return RetryResult(value=operation(), attempts=attempts, error=None)
        except Exception as exc:  # noqa: BLE001 - classified by is_transient
            permanent = not is_transient(exc)
            exhausted = attempts >= max_attempts
            if permanent or exhausted:
                return RetryResult(value=None, attempts=attempts, error=exc)
            sleeper(attempts)


class StageTimeoutError(RuntimeError):
    """A stage exceeded its wall-clock ``stage_timeout_seconds`` budget.

    Treated as transient by callers (a slow local model or a stalled
    retrieval may succeed on a later attempt), so it is safe to feed into
    ``call_with_retries`` alongside the transport timeouts. It never
    carries model output or memory content.
    """


def run_with_timeout(
    operation: Callable[[], Any],
    *,
    timeout_seconds: float,
) -> Any:
    """Run ``operation`` and abandon it if it exceeds ``timeout_seconds``.

    A synchronous, blocking local call (``httpx.post`` to loopback Ollama,
    a retrieval/embedding request) cannot be interrupted mid-flight without
    a framework, so this helper bounds it on a worker thread: the caller
    either gets the value or a :class:`StageTimeoutError` once the budget
    elapses. The abandoned worker keeps its own client-level timeout (the
    transport ``timeout=`` already set on every request), so it terminates
    on its own and cannot leak unbounded work.

    A non-positive ``timeout_seconds`` means "no extra bound" and the
    operation runs inline on the calling thread — the existing transport
    timeout remains the only guard. This keeps unit tests (which pass small
    or zero budgets) deterministic and avoids a thread hop for the common
    fast path.

    Raises:
        StageTimeoutError: the operation did not finish within the budget.
    """
    try:
        budget = float(timeout_seconds)
    except (TypeError, ValueError):
        budget = 0.0
    if budget <= 0:
        return operation()

    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(operation)
        try:
            return future.result(timeout=budget)
        except FutureTimeoutError as exc:
            raise StageTimeoutError(
                "The stage exceeded its time budget."
            ) from exc
    finally:
        # Do not block on the abandoned worker: it is bounded by its own
        # client timeout. shutdown(wait=False) lets the run continue.
        executor.shutdown(wait=False)
