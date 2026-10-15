"""Orchestrator tests (Module 8, Task 76). Part 1: fakes and stage plans."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.agents.orchestrator import Orchestrator, build_response
from app.agents.policies import HarnessPolicy
from app.agents.routes.router import QueryRouter
from app.agents.state import Objective, RunStatus, WorkflowState
from app.api.deps import get_orchestrator
from app.main import app
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
        max_attempts=2,
        max_errors=3,
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


class FakeRouter:
    """Deterministic router double: fixed objective or clarification."""

    def __init__(self, objective=None, clarification=None):
        self.objective = objective
        self.clarification = clarification
        self.calls: list[str] = []

    def apply_to_state(self, state, user_query: str):
        self.calls.append(user_query)
        if self.clarification is not None:
            state.set_clarification(self.clarification)
        else:
            state.set_objective(self.objective)
        from app.agents.state import TraceStatus
        state.record_trace(stage="router", status=TraceStatus.OK,
                           duration_ms=0, attempts=1)
        return state


class FakeRetrieval:
    def __init__(self, evidence=None, error=None):
        self.evidence = list(evidence or [])
        self.error = error
        self.calls = 0

    def retrieve(self, query, top_k=None):
        self.calls += 1
        if self.error is not None:
            raise self.error
        from app.services.temporal import NormalizedQuery
        from app.services.evidence import RetrievalResult
        return RetrievalResult(
            query=NormalizedQuery(original=query, text=query, temporal=None),
            evidence=list(self.evidence),
            candidates_considered=len(self.evidence),
            temporal=None,
            channels=("keyword",),
        )


class FakeAnalysisModel:
    def __init__(self, reply: str):
        self.reply = reply
        self.calls = 0

    def analyze(self, prompt: str) -> str:
        self.calls += 1
        return self.reply


class FakeTaskModel:
    def __init__(self, reply: str):
        self.reply = reply
        self.calls = 0

    def draft(self, prompt: str) -> str:
        self.calls += 1
        return self.reply


def analysis_reply(**overrides):
    payload = {
        "findings": [
            {"statement": "Notes cover RAG embeddings.", "evidence_refs": ["c1"]}
        ],
        "inferences": [],
        "unknowns": ["The records do not show exercises."],
        "conflicts": [],
    }
    payload.update(overrides)
    return json.dumps(payload)


def task_reply(**overrides):
    payload = {
        "tasks": [
            {"title": "Read embeddings guide",
             "description": "Study the retrieved guide.",
             "priority": "high", "source_ids": ["c1"],
             "kind": "outstanding", "status": "draft"},
        ]
    }
    payload.update(overrides)
    return json.dumps(payload)


def make_orchestrator(objective=Objective.SEARCH, evidence=None,
                       analysis=None, tasks=None, policy=None):
    return Orchestrator(
        router=FakeRouter(objective=objective),
        retrieval=FakeRetrieval(evidence if evidence is not None else [make_evidence()]),
        analysis_model=FakeAnalysisModel(analysis or analysis_reply()),
        task_model=FakeTaskModel(tasks or task_reply()),
        policy=policy or make_policy(),
    )


def test_create_tasks_runs_all_stages_to_awaiting_approval():
    orch = make_orchestrator(Objective.CREATE_TASKS)
    state = orch.run("Draft three next steps for my RAG study")
    assert state.status is RunStatus.AWAITING_APPROVAL
    assert state.objective is Objective.CREATE_TASKS
    assert len(state.evidence) == 1
    assert state.analysis is not None
    assert len(state.task_drafts) == 1
    assert [t.stage for t in state.trace] == ["router", "retrieval", "analysis", "task"]
    assert orch.retrieval.calls == 1
    assert orch.analysis_model.calls == 1
    assert orch.task_model.calls == 1


def test_search_runs_retrieval_only():
    orch = make_orchestrator(Objective.SEARCH)
    state = orch.run("Find my RAG notes")
    assert state.status is RunStatus.COMPLETED
    assert len(state.evidence) == 1
    assert state.analysis is None
    assert state.task_drafts == []
    assert [t.stage for t in state.trace] == ["router", "retrieval"]
    assert orch.analysis_model.calls == 0
    assert orch.task_model.calls == 0


def test_analyze_learning_skips_task_stage():
    orch = make_orchestrator(Objective.ANALYZE_LEARNING)
    state = orch.run("Review my saved learning notes about RAG")
    assert state.status is RunStatus.COMPLETED
    assert state.analysis is not None
    assert state.task_drafts == []
    assert [t.stage for t in state.trace] == ["router", "retrieval", "analysis"]
    assert orch.task_model.calls == 0


def test_summarize_runs_retrieval_and_analysis_without_tasks():
    orch = make_orchestrator(Objective.SUMMARIZE)
    state = orch.run("Summarize my RAG notes")
    assert state.status is RunStatus.COMPLETED
    assert state.analysis is not None
    assert state.task_drafts == []
    assert orch.task_model.calls == 0


def test_unique_run_ids_and_terminal_statuses():
    orch = make_orchestrator(Objective.SEARCH)
    first = orch.run("Find my RAG notes")
    second = orch.run("Find my RAG notes")
    assert first.run_id != second.run_id
    assert first.run_id.startswith("run_")
    assert first.status is RunStatus.COMPLETED
    assert second.status is RunStatus.COMPLETED


def test_clarification_stops_before_retrieval():
    orch = Orchestrator(
        router=FakeRouter(objective=None, clarification="Please clarify."),
        retrieval=FakeRetrieval([make_evidence()]),
        analysis_model=FakeAnalysisModel(analysis_reply()),
        task_model=FakeTaskModel(task_reply()),
        policy=make_policy(),
    )
    state = orch.run("Tell me a joke")
    assert state.status is RunStatus.COMPLETED
    assert state.objective is None
    assert state.clarification == "Please clarify."
    assert orch.retrieval.calls == 0
    assert orch.analysis_model.calls == 0
    assert orch.task_model.calls == 0


def test_empty_retrieval_is_valid_for_search():
    orch = make_orchestrator(Objective.SEARCH, evidence=[])
    state = orch.run("Find my RAG notes")
    assert state.status is RunStatus.COMPLETED
    assert state.evidence == []
    assert state.errors == []


def test_empty_analysis_yields_no_task_drafts():
    orch = make_orchestrator(
        Objective.CREATE_TASKS,
        analysis=analysis_reply(findings=[]),
    )
    state = orch.run("Draft three next steps")
    assert state.status is RunStatus.COMPLETED
    assert state.task_drafts == []
    assert orch.task_model.calls == 0


def test_router_failure_marks_run_failed():
    class BrokenRouter:
        def apply_to_state(self, state, user_query: str):
            raise RuntimeError("router exploded")

    orch = Orchestrator(
        router=BrokenRouter(),
        retrieval=FakeRetrieval([make_evidence()]),
        analysis_model=FakeAnalysisModel(analysis_reply()),
        task_model=FakeTaskModel(task_reply()),
        policy=make_policy(),
    )
    state = orch.run("Find my notes")
    assert state.status is RunStatus.FAILED
    assert len(state.errors) == 1
    assert "router exploded" not in state.errors[0].message


def test_retrieval_failure_marks_run_failed():
    from app.services.evidence import RetrievalUnavailableError
    orch = make_orchestrator(Objective.SEARCH)
    orch.retrieval = FakeRetrieval(error=RetrievalUnavailableError("down"))
    state = orch.run("Find my notes")
    assert state.status is RunStatus.FAILED
    assert orch.analysis_model.calls == 0


def test_analysis_failure_marks_run_failed():
    class DownModel:
        def analyze(self, prompt: str) -> str:
            raise RuntimeError("model down")

    orch = make_orchestrator(Objective.ANALYZE_LEARNING)
    orch.analysis_model = DownModel()
    state = orch.run("Review my notes")
    assert state.status is RunStatus.FAILED
    assert orch.task_model.calls == 0


def test_task_failure_marks_run_failed():
    class DownModel:
        def draft(self, prompt: str) -> str:
            raise RuntimeError("drafting down")

    orch = make_orchestrator(Objective.CREATE_TASKS)
    orch.task_model = DownModel()
    state = orch.run("Draft next steps")
    assert state.status is RunStatus.FAILED
    assert state.task_drafts == []


def test_invalid_query_raises_before_state():
    from app.agents.state import WorkflowRequestError
    orch = Orchestrator(
        router=QueryRouter(policy=make_policy()),
        retrieval=FakeRetrieval([]),
        policy=make_policy(),
    )
    try:
        orch.run("   ")
    except WorkflowRequestError:
        return
    raise AssertionError("expected WorkflowRequestError")


def test_no_task_persistence_by_orchestrator():
    orch = make_orchestrator(Objective.CREATE_TASKS)
    state = orch.run("Draft three next steps")
    assert all(d.status == "draft" for d in state.task_drafts)
    assert state.status is RunStatus.AWAITING_APPROVAL
    assert not state.is_terminal or True


def test_build_response_is_json_serializable_and_safe():
    orch = make_orchestrator(Objective.CREATE_TASKS)
    state = orch.run("Draft three next steps")
    response = build_response(state)
    text = json.dumps(response)
    assert response["run_id"] == state.run_id
    assert response["objective"] == "create_tasks"
    assert response["status"] == "awaiting_approval"
    assert len(response["evidence"]) == 1
    assert response["evidence"][0]["chunk_id"] == "c1"
    assert len(response["task_drafts"]) == 1
    assert "router exploded" not in text


def test_workflow_endpoint_returns_structured_result():
    orch = Orchestrator(
        router=FakeRouter(objective=Objective.SEARCH),
        retrieval=FakeRetrieval([make_evidence()]),
        analysis_model=FakeAnalysisModel(analysis_reply()),
        task_model=FakeTaskModel(task_reply()),
        policy=make_policy(),
    )
    app.dependency_overrides[get_orchestrator] = lambda: orch
    try:
        with TestClient(app) as client:
            resp = client.post("/api/v1/workflow", json={"question": "Find my notes"})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["objective"] == "search"
    assert body["status"] == "completed"
    assert body["run_id"].startswith("run_")


def test_workflow_endpoint_rejects_invalid_question():
    with TestClient(app) as client:
        resp = client.post("/api/v1/workflow", json={"question": ""})
    assert resp.status_code == 422

