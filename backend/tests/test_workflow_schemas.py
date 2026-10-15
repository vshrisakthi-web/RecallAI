"""Workflow schema tests (Module 8, Task 77). Part 1: helpers + request."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agents.orchestrator import Orchestrator, build_response
from app.agents.policies import HarnessPolicy
from app.agents.schemas import (
    RoutingResult,
    WorkflowResponse,
    validate_routing_result,
    validate_workflow_response,
)
from app.agents.state import Objective, RunStatus, WorkflowRequestError
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


def valid_payload(**overrides):
    payload = {
        "run_id": "run_abc123",
        "objective": "search",
        "status": "completed",
        "clarification": None,
        "findings": [],
        "evidence": [{
            "chunk_id": "c1", "memory_id": "m1", "source_title": "t",
            "source_url": None, "passage": "RAG uses embeddings.",
        }],
        "task_drafts": [],
        "errors": [],
        "trace": [{
            "stage": "retrieval", "status": "ok", "duration_ms": 3,
            "attempts": 1, "error_category": None,
        }],
    }
    payload.update(overrides)
    return payload


def test_valid_response_passes():
    response = validate_workflow_response(valid_payload())
    assert isinstance(response, WorkflowResponse)
    assert response.run_id == "run_abc123"
    assert response.status is RunStatus.COMPLETED


def test_valid_routing_results_pass():
    routed = validate_routing_result({
        "objective": Objective.SEARCH, "clarification": None,
        "confidence": 0.5, "ambiguity_score": 0.5,
    })
    assert routed["objective"] is Objective.SEARCH
    clarified = validate_routing_result({
        "objective": None, "clarification": "Please clarify.",
        "confidence": 0.0, "ambiguity_score": 1.0,
    })
    assert clarified["objective"] is None


def test_empty_and_whitespace_questions_rejected_by_endpoint():
    with TestClient(app) as client:
        assert client.post("/api/v1/workflow", json={"question": ""}).status_code == 422
        assert client.post("/api/v1/workflow", json={"question": "   "}).status_code == 422


def test_oversized_question_rejected_by_endpoint():
    with TestClient(app) as client:
        resp = client.post("/api/v1/workflow", json={"question": "x" * 1001})
    assert resp.status_code == 422


def test_missing_response_fields_rejected():
    payload = valid_payload()
    del payload["run_id"]
    with pytest.raises(ValidationError):
        validate_workflow_response(payload)


def test_invalid_objective_rejected():
    with pytest.raises(ValidationError):
        validate_workflow_response(valid_payload(objective="delete_everything"))


def test_invalid_status_rejected():
    with pytest.raises(ValidationError):
        validate_workflow_response(valid_payload(status="almost_done"))


def test_invalid_priority_and_kind_rejected():
    bad_priority = valid_payload(task_drafts=[{
        "title": "T", "description": "D", "priority": "urgent",
        "source_ids": ["c1"], "kind": "recommended", "status": "draft",
    }])
    with pytest.raises(ValidationError):
        validate_workflow_response(bad_priority)
    bad_kind = valid_payload(task_drafts=[{
        "title": "T", "description": "D", "priority": "high",
        "source_ids": ["c1"], "kind": "mandatory", "status": "draft",
    }])
    with pytest.raises(ValidationError):
        validate_workflow_response(bad_kind)


def test_extra_fields_rejected():
    payload = valid_payload()
    payload["actions"] = ["delete_everything"]
    with pytest.raises(ValidationError):
        validate_workflow_response(payload)
    routed = {"objective": "search", "clarification": None,
              "confidence": 0.5, "ambiguity_score": 0.5, "tools": ["shell"]}
    with pytest.raises(ValidationError):
        RoutingResult.model_validate(routed)


def test_fabricated_evidence_refs_rejected():
    payload = valid_payload(findings=[
        {"statement": "Something.", "evidence_refs": ["chunk_missing"]},
    ])
    with pytest.raises(Exception):
        validate_workflow_response(payload)


def test_drafts_referencing_missing_evidence_rejected():
    payload = valid_payload(task_drafts=[{
        "title": "T", "description": "D", "priority": "high",
        "source_ids": ["chunk_missing"], "kind": "recommended", "status": "draft",
    }])
    with pytest.raises(Exception):
        validate_workflow_response(payload)


def test_empty_evidence_with_fabricated_findings_rejected():
    payload = valid_payload(evidence=[], findings=[
        {"statement": "Something.", "evidence_refs": ["c1"]},
    ])
    with pytest.raises(Exception):
        validate_workflow_response(payload)


def test_clarification_must_not_carry_stage_results():
    bad = valid_payload(
        objective=None, clarification="Please clarify.",
        evidence=valid_payload()["evidence"],
    )
    with pytest.raises(ValidationError):
        validate_workflow_response(bad)
    bad2 = valid_payload(
        objective="search", clarification="Please clarify.",
    )
    with pytest.raises(ValidationError):
        validate_workflow_response(bad2)
    good = valid_payload(objective=None, clarification="Please clarify.", evidence=[])
    response = validate_workflow_response(good)
    assert response.objective is None


def test_router_result_requires_exactly_one_outcome():
    with pytest.raises(ValidationError):
        validate_routing_result({
            "objective": Objective.SEARCH, "clarification": "Both?",
            "confidence": 0.5, "ambiguity_score": 0.5,
        })
    with pytest.raises(ValidationError):
        validate_routing_result({
            "objective": None, "clarification": None,
            "confidence": 0.0, "ambiguity_score": 1.0,
        })


def test_malformed_agent_outputs_still_fail_safely():
    # Full malformed-output coverage lives in test_analysis_agent.py and
    # test_task_agent.py; here we prove garbage produces no state that
    # could pass response validation.
    from app.agents.analysis_agent import run_analysis
    from app.agents.state import Objective as Obj, WorkflowState

    class FakeModel:
        def analyze(self, prompt: str) -> str:
            return "not json {{{"

    state = WorkflowState.create("Review my notes", make_policy())
    state.set_objective(Obj.ANALYZE_LEARNING)
    state.evidence = [make_evidence()]
    with pytest.raises(Exception):
        run_analysis(state, FakeModel())
    assert state.analysis is None


def test_skipped_stage_objectives_validate():
    search = valid_payload(objective="search", status="completed")
    assert validate_workflow_response(search).findings == []
    summarize = valid_payload(objective="summarize", status="completed")
    assert validate_workflow_response(summarize).task_drafts == []


def test_invalid_output_causes_safe_failure_not_silent_success():
    from app.agents.orchestrator import Orchestrator, build_response
    from app.services.evidence import RetrievalUnavailableError

    class FakeRouter:
        def apply_to_state(self, state, user_query: str):
            from app.agents.state import Objective as Obj, TraceStatus
            state.set_objective(Obj.SEARCH)
            state.record_trace(stage="router", status=TraceStatus.OK,
                               duration_ms=0, attempts=1)
            return state

    class FailingRetrieval:
        def retrieve(self, query, top_k=None):
            raise RetrievalUnavailableError("down")

    orch = Orchestrator(router=FakeRouter(), retrieval=FailingRetrieval(),
                        policy=make_policy())
    state = orch.run("Find my notes")
    assert state.status.value == "failed"
    response = validate_workflow_response(build_response(state))
    assert response.status.value == "failed"


def test_orchestrator_output_passes_response_validation():
    import json as jsonlib
    from app.agents.orchestrator import Orchestrator, build_response

    class FakeRouter:
        def apply_to_state(self, state, user_query: str):
            from app.agents.state import Objective as Obj, TraceStatus
            state.set_objective(Obj.SEARCH)
            state.record_trace(stage="router", status=TraceStatus.OK,
                               duration_ms=0, attempts=1)
            return state

    class FakeRetrieval:
        def retrieve(self, query, top_k=None):
            from app.services.evidence import RetrievalResult
            from app.services.temporal import NormalizedQuery
            return RetrievalResult(
                query=NormalizedQuery(original=query, text=query, temporal=None),
                evidence=[make_evidence()],
                candidates_considered=1, temporal=None, channels=("keyword",),
            )

    orch = Orchestrator(router=FakeRouter(), retrieval=FakeRetrieval(),
                        policy=make_policy())
    state = orch.run("Find my RAG notes")
    response = validate_workflow_response(build_response(state))
    assert response.objective.value == "search"
    jsonlib.dumps(response.model_dump(mode="json"))


def test_endpoint_returns_validated_shape():
    from app.agents.orchestrator import Orchestrator

    class FakeRouter:
        def apply_to_state(self, state, user_query: str):
            from app.agents.state import Objective as Obj, TraceStatus
            state.set_objective(Obj.SEARCH)
            state.record_trace(stage="router", status=TraceStatus.OK,
                               duration_ms=0, attempts=1)
            return state

    class FakeRetrieval:
        def retrieve(self, query, top_k=None):
            from app.services.evidence import RetrievalResult
            from app.services.temporal import NormalizedQuery
            return RetrievalResult(
                query=NormalizedQuery(original=query, text=query, temporal=None),
                evidence=[make_evidence()],
                candidates_considered=1, temporal=None, channels=("keyword",),
            )

    orch = Orchestrator(router=FakeRouter(), retrieval=FakeRetrieval(),
                        policy=make_policy())
    app.dependency_overrides[get_orchestrator] = lambda: orch
    try:
        with TestClient(app) as client:
            resp = client.post("/api/v1/workflow", json={"question": "Find my notes"})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    validate_workflow_response(body)
    assert body["objective"] == "search"
    assert set(body) == {"run_id", "objective", "status", "clarification",
                         "findings", "evidence", "task_drafts", "errors", "trace"}


def test_validation_adds_no_persistence():
    payload = valid_payload()
    validate_workflow_response(payload)
    assert "persisted" not in json.dumps(payload)
    assert payload["task_drafts"] == []
