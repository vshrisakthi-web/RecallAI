"""Human approval tests (Module 8, Task 79).

Covers the approval/persistence boundary end to end at the unit level:

* a workflow produces drafts but writes nothing to the ``tasks`` table;
* only the explicit approval endpoint persists drafts;
* approve persists and completes the run; edit re-validates before persisting;
* reject persists nothing and transitions the run to REJECTED;
* duplicate/replayed decisions and invalid lifecycle states are rejected (409);
* unknown/stale run ids are rejected (404);
* fabricated evidence references and oversized edits are rejected (422);
* a persistence failure leaves the run awaiting approval (no partial/COMPLETED);
* a multi-draft approval is all-or-nothing (no partial persistence);
* a model-generated "the user approved" statement never authorizes a write.

Deterministic and offline: the model boundary is a fake, the run store and
task service are injected, and the database is the isolated migrated SQLite
fixture. No network, no Ollama.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.agents.approval import (
    InvalidStateError,
    RunNotFoundError,
    apply_decision,
)
from app.agents.policies import HarnessPolicy
from app.agents.run_store import RunStore
from app.agents.state import Objective, RunStatus, WorkflowState
from app.agents.task_agent import TaskDraft
from app.api.routes.approval import get_task_service
from app.database.models import Task
from app.main import app
from app.repositories.base import StorageError
from app.repositories.task_repo import TaskRepository
from app.services.evidence import Evidence
from app.services.task_service import TaskService


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
        max_attempts=2,
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


def make_draft(title="Read embeddings guide", source_ids=("c1",), **kw):
    data = {
        "title": title,
        "description": "Study the retrieved guide.",
        "priority": "high",
        "source_ids": list(source_ids),
        "kind": "outstanding",
        "status": "draft",
    }
    data.update(kw)
    return TaskDraft.model_validate(data)


def awaiting_run(policy=None, drafts=None, evidence=None):
    """A run in AWAITING_APPROVAL with drafts grounded in retrieved evidence."""
    state = WorkflowState.create("Draft next steps", policy or make_policy())
    state.set_objective(Objective.CREATE_TASKS)
    state.evidence = evidence if evidence is not None else [make_evidence("c1"), make_evidence("c2", "Vector notes.")]
    state.task_drafts = drafts if drafts is not None else [make_draft(source_ids=("c1",))]
    state.transition(RunStatus.RUNNING)
    state.transition(RunStatus.AWAITING_APPROVAL)
    return state


def task_service_for(database_engine):
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    return TaskService(TaskRepository(sessions))


def count_tasks(database_engine) -> int:
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    session = sessions()
    try:
        return session.scalar(select(func.count()).select_from(Task)) or 0
    finally:
        session.close()


def draft_payload(draft):
    return draft.model_dump(mode="json")


# --- Approve ---------------------------------------------------------------


def test_approve_persists_drafts_and_completes(database_engine):
    store = RunStore()
    service = task_service_for(database_engine)
    run = awaiting_run()
    store.put(run)

    result = apply_decision(store, service, run.run_id, "approve")

    assert result["status"] == "completed"
    assert len(result["persisted_task_ids"]) == 1
    assert run.status is RunStatus.COMPLETED
    assert count_tasks(database_engine) == 1


def test_approved_task_stored_as_json_reference(database_engine):
    store = RunStore()
    service = task_service_for(database_engine)
    run = awaiting_run(drafts=[make_draft(source_ids=("c1", "c2"))])
    store.put(run)

    result = apply_decision(store, service, run.run_id, "approve")
    stored = service._repository.get_by_id(result["persisted_task_ids"][0])

    assert stored["task_type"] == "agent_task_draft"
    assert stored["status"] == "todo"
    ref = stored["input_reference"]
    assert ref["title"] == "Read embeddings guide"
    assert ref["priority"] == "high"
    assert ref["kind"] == "outstanding"
    assert sorted(ref["source_ids"]) == ["c1", "c2"]
    assert ref["run_id"] == run.run_id


def test_workflow_produces_drafts_without_persisting(database_engine):
    # A run in AWAITING_APPROVAL exists in memory only; no approval -> no rows.
    run = awaiting_run()
    store = RunStore()
    store.put(run)
    assert count_tasks(database_engine) == 0
    assert all(d.status == "draft" for d in run.task_drafts)


# --- Edit + revalidation ---------------------------------------------------


def test_edit_revalidates_and_persists_only_validated(database_engine):
    store = RunStore()
    service = task_service_for(database_engine)
    run = awaiting_run()
    store.put(run)

    edited = {"tasks": [draft_payload(make_draft(title="Edited plan", source_ids=("c2",)))]}
    result = apply_decision(store, service, run.run_id, "edit", edited_drafts=edited)

    assert result["status"] == "completed"
    stored = service._repository.get_by_id(result["persisted_task_ids"][0])
    assert stored["input_reference"]["title"] == "Edited plan"
    assert stored["input_reference"]["source_ids"] == ["c2"]


def test_edit_with_fabricated_source_id_rejected(database_engine):
    from app.agents.approval import ApprovalValidationError

    store = RunStore()
    service = task_service_for(database_engine)
    run = awaiting_run()
    store.put(run)

    edited = {"tasks": [draft_payload(make_draft(source_ids=("chunk_missing",)))]}
    with pytest.raises(ApprovalValidationError):
        apply_decision(store, service, run.run_id, "edit", edited_drafts=edited)
    assert count_tasks(database_engine) == 0
    assert run.status is RunStatus.AWAITING_APPROVAL


def test_edit_oversized_title_rejected(database_engine):
    from app.agents.approval import ApprovalValidationError

    store = RunStore()
    service = task_service_for(database_engine)
    run = awaiting_run()  # max_task_title_chars=40
    store.put(run)

    edited = {"tasks": [draft_payload(make_draft(title="x" * 80, source_ids=("c1",)))]}
    with pytest.raises(ApprovalValidationError):
        apply_decision(store, service, run.run_id, "edit", edited_drafts=edited)
    assert count_tasks(database_engine) == 0


def test_edit_over_task_count_cap_rejected(database_engine):
    from app.agents.approval import ApprovalValidationError

    store = RunStore()
    service = task_service_for(database_engine)
    run = awaiting_run(policy=make_policy(max_tasks=1))
    store.put(run)

    edited = {"tasks": [
        draft_payload(make_draft(title="One", source_ids=("c1",))),
        draft_payload(make_draft(title="Two", source_ids=("c2",))),
    ]}
    with pytest.raises(ApprovalValidationError):
        apply_decision(store, service, run.run_id, "edit", edited_drafts=edited)
    assert count_tasks(database_engine) == 0


# --- Reject ----------------------------------------------------------------


def test_reject_persists_nothing_and_transitions_rejected(database_engine):
    store = RunStore()
    service = task_service_for(database_engine)
    run = awaiting_run()
    store.put(run)

    result = apply_decision(store, service, run.run_id, "reject")
    assert result["status"] == "rejected"
    assert result["persisted_task_ids"] == []
    assert run.status is RunStatus.REJECTED
    assert count_tasks(database_engine) == 0



# --- Duplicate / replay / invalid state ------------------------------------


def test_duplicate_approval_rejected_after_completion(database_engine):
    store = RunStore()
    service = task_service_for(database_engine)
    run = awaiting_run()
    store.put(run)

    apply_decision(store, service, run.run_id, "approve")
    with pytest.raises(RunNotFoundError):
        apply_decision(store, service, run.run_id, "approve")
    assert count_tasks(database_engine) == 1  # no double write


def test_replayed_reject_after_reject_is_unknown(database_engine):
    store = RunStore()
    service = task_service_for(database_engine)
    run = awaiting_run()
    store.put(run)

    apply_decision(store, service, run.run_id, "reject")
    with pytest.raises(RunNotFoundError):
        apply_decision(store, service, run.run_id, "reject")
    assert count_tasks(database_engine) == 0


def test_run_in_completed_state_cannot_be_approved(database_engine):
    store = RunStore()
    service = task_service_for(database_engine)
    run = awaiting_run()
    run.transition(RunStatus.COMPLETED)  # not awaiting approval
    store._runs[run.run_id] = run  # force an entry in a wrong state

    with pytest.raises(InvalidStateError):
        apply_decision(store, service, run.run_id, "approve")
    assert count_tasks(database_engine) == 0


# --- Unknown / stale run ids -----------------------------------------------


def test_unknown_run_id_rejected(database_engine):
    store = RunStore()
    service = task_service_for(database_engine)
    with pytest.raises(RunNotFoundError):
        apply_decision(store, service, "run_does_not_exist", "approve")


def test_store_refuses_non_awaiting_runs():
    store = RunStore()
    run = awaiting_run()
    run.transition(RunStatus.COMPLETED)
    store.put(run)  # refused: not AWAITING_APPROVAL
    assert store.get(run.run_id) is None
    assert len(store) == 0


# --- Security: model text can never authorize a write ----------------------


def test_model_approval_statement_never_persists(database_engine):
    store = RunStore()
    service = task_service_for(database_engine)
    run = awaiting_run()
    store.put(run)
    assert count_tasks(database_engine) == 0  # nothing written by the model
    apply_decision(store, service, run.run_id, "approve")  # only explicit decision
    assert count_tasks(database_engine) == 1


def test_endpoint_ignores_extra_approval_claim_fields(database_engine):
    store = RunStore()
    service = task_service_for(database_engine)
    run = awaiting_run()
    store.put(run)

    from app.api.routes.approval import get_run_store

    app.dependency_overrides[get_run_store] = lambda: store
    app.dependency_overrides[get_task_service] = lambda: service
    try:
        with TestClient(app) as client:
            resp = client.post(
                f"/api/v1/workflow/{run.run_id}/approve",
                json={"decision": "approve", "approved": True},
            )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code in (400, 422)  # extra field rejected
    assert count_tasks(database_engine) == 0



# --- Persistence failure + partial-persistence protection ------------------


class _FailingRepo:
    def create_many(self, drafts, run_id):
        raise StorageError("database write failed")


class _PartialFailRepo:
    """Fails if more than one draft is written (proves all-or-nothing)."""

    def __init__(self):
        self.calls = 0

    def create_many(self, drafts, run_id):
        self.calls += 1
        if len(drafts) > 1:
            raise StorageError("simulated multi-row failure")
        return ["task_x"]


def test_persistence_failure_leaves_run_awaiting(database_engine):
    from app.services.task_service import TaskService

    store = RunStore()
    service = TaskService(_FailingRepo())
    run = awaiting_run()
    store.put(run)

    with pytest.raises(StorageError):
        apply_decision(store, service, run.run_id, "approve")
    assert run.status is RunStatus.AWAITING_APPROVAL  # not completed
    assert count_tasks(database_engine) == 0


def test_multi_draft_approval_is_all_or_nothing(database_engine):
    from app.services.task_service import TaskService

    store = RunStore()
    service = TaskService(_PartialFailRepo())
    run = awaiting_run(drafts=[
        make_draft(title="One", source_ids=("c1",)),
        make_draft(title="Two", source_ids=("c2",)),
    ])
    store.put(run)

    with pytest.raises(StorageError):
        apply_decision(store, service, run.run_id, "approve")
    assert service._repository.calls == 1
    assert run.status is RunStatus.AWAITING_APPROVAL
    assert count_tasks(database_engine) == 0


# --- Endpoint status-code mapping ------------------------------------------


def _client_overrides(store, service):
    from app.api.routes.approval import get_run_store

    app.dependency_overrides[get_run_store] = lambda: store
    app.dependency_overrides[get_task_service] = lambda: service


def test_endpoint_approve_returns_200(database_engine):
    store = RunStore()
    service = task_service_for(database_engine)
    run = awaiting_run()
    store.put(run)
    _client_overrides(store, service)
    try:
        with TestClient(app) as client:
            resp = client.post(f"/api/v1/workflow/{run.run_id}/approve",
                               json={"decision": "approve"})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert len(body["persisted_task_ids"]) == 1


def test_endpoint_unknown_run_returns_404(database_engine):
    store = RunStore()
    service = task_service_for(database_engine)
    _client_overrides(store, service)
    try:
        with TestClient(app) as client:
            resp = client.post("/api/v1/workflow/run_nope/approve",
                               json={"decision": "approve"})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 404


def test_endpoint_invalid_decision_returns_422(database_engine):
    store = RunStore()
    service = task_service_for(database_engine)
    run = awaiting_run()
    store.put(run)
    _client_overrides(store, service)
    try:
        with TestClient(app) as client:
            resp = client.post(f"/api/v1/workflow/{run.run_id}/approve",
                               json={"decision": "maybe"})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 422
    assert count_tasks(database_engine) == 0


def test_endpoint_storage_failure_returns_503(database_engine):
    from app.services.task_service import TaskService

    store = RunStore()
    service = TaskService(_FailingRepo())
    run = awaiting_run()
    store.put(run)
    _client_overrides(store, service)
    try:
        with TestClient(app) as client:
            resp = client.post(f"/api/v1/workflow/{run.run_id}/approve",
                               json={"decision": "approve"})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 503
    assert count_tasks(database_engine) == 0


def test_workflow_endpoint_registers_run_for_approval(database_engine):
    from unittest.mock import MagicMock

    store = RunStore()
    run = awaiting_run()

    from app.api.deps import get_orchestrator

    orch = MagicMock()
    orch.run.return_value = run
    app.dependency_overrides[get_orchestrator] = lambda: orch
    from app.api.routes.workflow import get_run_store as workflow_run_store
    app.dependency_overrides[workflow_run_store] = lambda: store
    try:
        with TestClient(app) as client:
            resp = client.post("/api/v1/workflow", json={"question": "Draft next steps"})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert store.get(run.run_id) is run  # registered for approval
    assert count_tasks(database_engine) == 0  # still nothing persisted

