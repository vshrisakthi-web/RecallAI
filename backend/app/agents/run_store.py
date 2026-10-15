"""In-process run registry for human approval (Module 8, Task 79).

Plain English: a workflow that ends with proposed task drafts rests in
``AWAITING_APPROVAL``. To approve it, the approval endpoint must be able to
find that run again by its ``run_id``. This module is that tiny, in-process
registry: it holds only runs awaiting approval, keyed by ``run_id``, and
evicts the oldest once capacity is reached.

Design decisions:

* Only runs in ``AWAITING_APPROVAL`` are ever stored (``put`` refuses any
  other status). Search/summarize/analyze runs and failed or completed runs
  are never registered — there is nothing to approve on them.
* Bounded capacity (``max_runs``, oldest evicted first) so a long-lived
  process cannot grow without limit.
* Transient by design: this is process-local memory, **not** durable storage.
  Pending approvals are lost if the server restarts. That is an intentional,
  documented limitation of the local single-process app, not a bug — no
  approved task is ever at risk, because persistence happens only at approval
  time and writes to the durable ``tasks`` table.
* The registry stores only validated workflow state; it never re-validates or
  trusts model text. The approval layer re-checks status and evidence before
  any write.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Optional

from app.agents.state import RunStatus, WorkflowState

# Default number of pending runs kept in memory. Small on purpose: this is a
# local, single-process app where a handful of concurrent approvals is normal.
_DEFAULT_MAX_RUNS = 64


class RunStore:
    """A bounded, in-memory registry of runs awaiting approval.

    Not thread-safe by internal locking (the local dev server runs the
    approval endpoint synchronously); the state-machine check in the approval
    layer, not this store, is what prevents a run from being approved twice.
    """

    def __init__(self, max_runs: int = _DEFAULT_MAX_RUNS) -> None:
        if max_runs < 1:
            raise ValueError("RunStore capacity must be at least 1.")
        self._max_runs = max_runs
        self._runs: "OrderedDict[str, WorkflowState]" = OrderedDict()

    @property
    def max_runs(self) -> int:
        return self._max_runs

    def __len__(self) -> int:
        return len(self._runs)

    def put(self, state: WorkflowState) -> None:
        """Register a run that is awaiting approval.

        Refuses anything not in ``AWAITING_APPROVAL`` so a completed, failed,
        or clarification run can never be stored for later "approval". On
        overflow the oldest entry is evicted first.
        """
        if state.status is not RunStatus.AWAITING_APPROVAL:
            return
        run_id = state.run_id
        # Re-insert to move to the most-recent end on update.
        if run_id in self._runs:
            self._runs.move_to_end(run_id)
        self._runs[run_id] = state
        while len(self._runs) > self._max_runs:
            self._runs.popitem(last=False)

    def get(self, run_id: str) -> Optional[WorkflowState]:
        """Return the stored run for ``run_id``, or ``None`` if unknown."""
        if not isinstance(run_id, str) or not run_id:
            return None
        return self._runs.get(run_id)

    def remove(self, run_id: str) -> None:
        """Forget a run (used after it reaches a terminal state)."""
        self._runs.pop(run_id, None)


# Module-level default instance used by the FastAPI dependency. Tests override
# it via ``app.dependency_overrides`` so they never share production state.
_default_run_store = RunStore()


def get_default_run_store() -> RunStore:
    """Return the process-wide run registry (the production default)."""
    return _default_run_store
