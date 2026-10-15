"""Task Agent tests (Module 8, Task 75). Part 1: helpers and happy paths."""

from __future__ import annotations

import json

import httpx
import pytest

from app.agents.analysis_agent import AnalysisResult
from app.agents.contracts import UnknownEvidenceError
from app.agents.policies import HarnessPolicy
from app.agents.state import Objective, TraceStatus, WorkflowState
from app.agents.task_agent import (
    OllamaTaskModel,
    TaskDraft,
    TaskKind,
    TaskModelUnavailableError,
    TaskResponseError,
    build_task_prompt,
    parse_and_validate,
    run_tasks,
)
from app.core.config import Settings
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


def make_analysis(with_findings=True):
    if with_findings:
        return AnalysisResult.model_validate({
            "findings": [
                {"statement": "Notes cover RAG embeddings.", "evidence_refs": ["c1"]},
                {"statement": "Notes cover vector search.", "evidence_refs": ["c2"]},
            ],
            "inferences": [],
            "unknowns": ["The records do not show exercises."],
            "conflicts": [],
        })
    return AnalysisResult.model_validate({
        "findings": [], "inferences": [], "unknowns": [], "conflicts": [],
    })


def make_state(policy=None, with_findings=True):
    state = WorkflowState.create("Draft next steps", policy or make_policy())
    state.set_objective(Objective.CREATE_TASKS)
    state.evidence = [make_evidence("c1"), make_evidence("c2", "Vector search notes.")]
    state.analysis = make_analysis(with_findings)
    return state


class FakeModel:
    def __init__(self, reply: str):
        self.reply = reply
        self.calls: list[str] = []

    def draft(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.reply


def valid_reply(**overrides):
    payload = {
        "tasks": [
            {"title": "Read embeddings guide", "description": "Study the retrieved guide.",
             "priority": "high", "source_ids": ["c1"], "kind": "outstanding",
             "status": "draft"},
            {"title": "Try vector search", "description": "Run a small search test.",
             "priority": "medium", "source_ids": ["c2"], "kind": "recommended",
             "status": "draft"},
        ]
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_valid_drafts_stored_with_trace():
    state = make_state()
    run_tasks(state, FakeModel(valid_reply()))
    assert len(state.task_drafts) == 2
    assert all(isinstance(d, TaskDraft) for d in state.task_drafts)
    assert all(d.status == "draft" for d in state.task_drafts)
    assert state.task_drafts[0].kind is TaskKind.OUTSTANDING
    assert state.trace[-1].stage == "task"
    assert state.trace[-1].status is TraceStatus.OK


def test_empty_findings_skip_model_with_empty_drafts():
    state = make_state(with_findings=False)
    model = FakeModel(valid_reply())
    run_tasks(state, model)
    assert model.calls == []
    assert state.task_drafts == []
    assert state.trace[-1].status is TraceStatus.OK


def test_contradictory_analysis_still_drafts_from_findings():
    state = make_state()
    state.analysis = AnalysisResult.model_validate({
        "findings": [{"statement": "Notes cover RAG.", "evidence_refs": ["c1"]}],
        "inferences": [],
        "unknowns": [],
        "conflicts": [{"description": "Storage differs.", "evidence_refs": ["c1", "c2"]}],
    })
    run_tasks(state, FakeModel(valid_reply(tasks=[
        {"title": "Resolve storage notes", "description": "Compare both excerpts.",
         "priority": "high", "source_ids": ["c1", "c2"],
         "kind": "recommended", "status": "draft"},
    ])))
    assert len(state.task_drafts) == 1
    assert sorted(state.task_drafts[0].source_ids) == ["c1", "c2"]


def test_unknown_source_id_rejected():
    state = make_state()
    reply = valid_reply(tasks=[
        {"title": "Bad draft", "description": "Cites nothing real.",
         "priority": "high", "source_ids": ["chunk_missing"],
         "kind": "recommended", "status": "draft"},
    ])
    with pytest.raises(UnknownEvidenceError):
        run_tasks(state, FakeModel(reply))
    assert state.task_drafts == []
    assert state.trace[-1].error_category == "unknown_evidence"


def test_malformed_output_rejected():
    state = make_state()
    with pytest.raises(TaskResponseError):
        run_tasks(state, FakeModel("not json {{{"))
    assert state.task_drafts == []
    assert state.trace[-1].error_category == "invalid_response"


def test_missing_fields_rejected():
    state = make_state()
    with pytest.raises(Exception):
        run_tasks(state, FakeModel(json.dumps({"wrong_key": []})))
    assert state.task_drafts == []


def test_invalid_enum_rejected():
    state = make_state()
    reply = valid_reply(tasks=[
        {"title": "Bad priority", "description": "Bad enum value.",
         "priority": "urgent", "source_ids": ["c1"],
         "kind": "recommended", "status": "draft"},
    ])
    with pytest.raises(Exception):
        run_tasks(state, FakeModel(reply))
    assert state.task_drafts == []


def test_evidence_free_drafts_rejected():
    state = make_state()
    reply = valid_reply(tasks=[
        {"title": "No support", "description": "No refs at all.",
         "priority": "low", "source_ids": [],
         "kind": "recommended", "status": "draft"},
    ])
    with pytest.raises(Exception):
        run_tasks(state, FakeModel(reply))
    assert state.task_drafts == []


def test_duplicate_drafts_collapsed():
    state = make_state()
    task = {"title": "Read guide", "description": "Study it.",
            "priority": "high", "source_ids": ["c1"],
            "kind": "recommended", "status": "draft"}
    run_tasks(state, FakeModel(valid_reply(tasks=[task, dict(task)])))
    assert len(state.task_drafts) == 1


def test_count_capped_at_policy_max():
    state = make_state(policy=make_policy(max_tasks=1))
    run_tasks(state, FakeModel(valid_reply()))
    assert len(state.task_drafts) == 1


def test_oversized_title_rejected():
    state = make_state()
    reply = valid_reply(tasks=[
        {"title": "x" * 200, "description": "Too long.",
         "priority": "high", "source_ids": ["c1"],
         "kind": "recommended", "status": "draft"},
    ])
    with pytest.raises(TaskResponseError):
        run_tasks(state, FakeModel(reply))
    assert state.task_drafts == []


def test_model_unavailable_records_safe_error():
    state = make_state()

    class DownModel:
        def draft(self, prompt: str) -> str:
            raise TaskModelUnavailableError("daemon down")

    with pytest.raises(TaskModelUnavailableError):
        run_tasks(state, DownModel())
    assert state.errors[-1].category == "unavailable"
    assert "daemon down" not in state.errors[-1].message
    assert state.task_drafts == []
    assert state.trace[-1].status is TraceStatus.ERROR


def test_task_agent_never_persists():
    state = make_state()
    run_tasks(state, FakeModel(valid_reply()))
    assert state.status.value == "pending"
    assert all(d.status == "draft" for d in state.task_drafts)


def test_missing_inputs_raise_before_model_call():
    state = WorkflowState.create("Draft steps", make_policy())
    model = FakeModel(valid_reply())
    with pytest.raises(Exception):
        run_tasks(state, model)
    assert model.calls == []


def test_prompt_treats_analysis_as_data():
    prompt = build_task_prompt("Draft steps", "create_tasks", make_analysis())
    assert "untrusted data" in prompt
    assert "never persist" in prompt.lower()


def test_ollama_model_posts_to_loopback_without_credentials():
    calls: list = []

    def fake_post(url: str, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(
            200,
            json={"message": {"content": valid_reply()}, "done": True},
            request=httpx.Request("POST", url),
        )

    config = Settings(
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="unit-test-model",
    )
    out = OllamaTaskModel(config=config, post=fake_post).draft("prompt")
    assert json.loads(out)["tasks"]
    url, kwargs = calls[0]
    assert url == "http://127.0.0.1:11434/api/chat"
    assert all("key" not in name.lower() for name in kwargs["headers"])


def test_parse_and_validate_accepts_minimal_payload():
    drafts = parse_and_validate(
        json.dumps({"tasks": []}), [make_evidence()], make_policy()
    )
    assert drafts == []
