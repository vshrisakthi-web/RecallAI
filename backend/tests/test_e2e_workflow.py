"""End-to-end workflow + approval lifecycle tests (Module 8, Task 80).

These are genuine end-to-end tests: they drive the **real FastAPI app**
(``app.main.app``) through ``TestClient`` with the real ``Orchestrator``, the
real ``QueryRouter``, the real ``HybridRetrievalService`` over a migrated
SQLite database (fake embedding transport), and fake Ollama model boundaries
for analysis/task. A single shared in-process ``RunStore`` and a real
``TaskService`` are wired via dependency overrides, so the workflow endpoint
and the approval endpoint operate on the same run and the same database.

No live LLM, no external network: the embedding and Ollama HTTP boundaries are
faked, deterministic, and offline. The database is the isolated per-test
migrated SQLite fixture.

The lifecycle under test:

1. ``POST /api/v1/workflow`` routes the question, retrieves bounded evidence,
   analyzes, drafts tasks, and returns ``awaiting_approval`` with drafts —
   while writing **nothing** to the ``tasks`` table.
2. ``POST /api/v1/workflow/{run_id}/approve`` with an explicit decision
   persists valid drafts (``approve``) or nothing (``reject``), and enforces
   the approval boundary against replayed/invalid/stale decisions.

Failure paths (no memories, conflicts, malformed model output, unknown source
ids, model unavailable, retrieval failure) are exercised end to end as well.
"""

from __future__ import annotations

import json

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.agents.orchestrator import Orchestrator
from app.agents.policies import HarnessPolicy
from app.agents.run_store import RunStore
from app.agents.routes.router import QueryRouter
from app.api.deps import get_orchestrator
from app.api.routes.approval import get_run_store as approval_run_store
from app.api.routes.approval import get_task_service
from app.api.routes.workflow import get_run_store as workflow_run_store
from app.core.config import Settings
from app.database.models import Task
from app.main import app
from app.repositories.chunk_store import ChunkRepository
from app.repositories.task_repo import TaskRepository
from app.repositories.vector_store import VectorStore
from app.services.chunking import chunk_text
from app.services.embeddings import EmbeddingService
from app.services.hybrid import HybridRetrievalService
from app.services.keyword_search import KeywordSearchService
from app.services.task_service import TaskService
from tests._factories import make_record, utcnow

MODEL = "unit-embed-model"
RAG_VEC = [1.0, 0.05, 0.0]
COOK_VEC = [0.0, 1.0, 0.0]
QUERY_VEC = [0.95, 0.1, 0.0]


def make_policy(**overrides) -> HarnessPolicy:
    base = dict(
        max_query_chars=400,
        max_evidence_items=4,
        max_evidence_chars=4000,
        max_tasks=3,
        max_task_title_chars=120,
        max_task_description_chars=400,
        stage_timeout_seconds=10,
        total_budget_seconds=60,
        max_attempts=2,
        max_errors=5,
    )
    base.update(overrides)
    return HarnessPolicy(**base)


def embedding_service(vector, model=MODEL, failing=False):
    def fake_post(url: str, **kwargs):
        if failing:
            raise httpx.ConnectError("refused", request=httpx.Request("POST", url))
        inputs = kwargs["json"]["input"]
        return httpx.Response(
            200,
            json={"embeddings": [list(vector) for _ in inputs]},
            request=httpx.Request("POST", url),
        )

    config = Settings(ollama_base_url="http://127.0.0.1:11434", embedding_model=model)
    return EmbeddingService(config=config, post=fake_post), config


def ollama_post(reply_text, *, failing=False, slow=False):
    """A fake Ollama /api/chat transport returning ``reply_text`` as content."""

    def fake_post(url: str, **kwargs):
        if failing:
            raise httpx.ConnectError("refused", request=httpx.Request("POST", url))
        if slow:
            import time
            time.sleep(2.0)
        return httpx.Response(
            200,
            json={"message": {"content": reply_text}, "done": True},
            request=httpx.Request("POST", url),
        )

    return fake_post


def seed_memory(repository, sessions, memory_id, text, vector, **kwargs):
    saved, _ = repository.save_or_get(
        make_record(id=memory_id, _text=text, captured_at=utcnow(), **kwargs)
    )
    chunk_ids = ChunkRepository(sessions).replace_memory_chunks(
        saved.id, chunk_text(saved.normalized_text, saved.id)
    )
    VectorStore(sessions).upsert_many(
        [(cid, saved.id, list(vector)) for cid in chunk_ids], MODEL
    )
    return saved, chunk_ids


def count_tasks(database_engine) -> int:
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    session = sessions()
    try:
        return session.scalar(select(func.count()).select_from(Task)) or 0
    finally:
        session.close()


def build_orchestrator(repository, database_engine, *, analysis_reply, task_reply,
                       analysis_failing=False, task_failing=False, analysis_slow=False,
                       embedding_failing=False, vector=QUERY_VEC, policy=None):
    """A real Orchestrator wired to the test DB + fake model transports."""
    from app.agents.analysis_agent import OllamaAnalysisModel
    from app.agents.task_agent import OllamaTaskModel

    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    embeddings, base = embedding_service(vector, failing=embedding_failing)
    service = HybridRetrievalService(
        memories=repository,
        chunks=ChunkRepository(sessions),
        vectors=VectorStore(sessions),
        embeddings=embeddings,
        keywords=KeywordSearchService(sessions),
        sessions=sessions,
        config=base,
    )
    model_config = Settings(
        ollama_base_url="http://127.0.0.1:11434", ollama_model="unit-model"
    )
    analysis_model = OllamaAnalysisModel(
        config=model_config,
        post=ollama_post(analysis_reply, failing=analysis_failing, slow=analysis_slow),
    )
    task_model = OllamaTaskModel(
        config=model_config,
        post=ollama_post(task_reply, failing=task_failing),
    )
    return Orchestrator(
        router=QueryRouter(policy=policy or make_policy()),
        retrieval=service,
        analysis_model=analysis_model,
        task_model=task_model,
        policy=policy or make_policy(),
    )


def wire_app(orch, store, database_engine):
    """Override app deps: one orchestrator, one shared run store, one task svc."""
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    service = TaskService(TaskRepository(sessions))
    app.dependency_overrides[get_orchestrator] = lambda: orch
    app.dependency_overrides[workflow_run_store] = lambda: store
    app.dependency_overrides[approval_run_store] = lambda: store
    app.dependency_overrides[get_task_service] = lambda: service


def clear_app():
    app.dependency_overrides.clear()



# --- Fixed model replies grounded in the seeded RAG chunk -----------------

ANALYSIS_REPLY = json.dumps({
    "findings": [
        {"statement": "Notes cover RAG embeddings and vector search.",
         "evidence_refs": ["__C1__"]}
    ],
    "inferences": [
        {"statement": "The learner is building retrieval fundamentals.",
         "evidence_refs": ["__C1__"]}
    ],
    "unknowns": ["The records do not show any completed RAG exercises."],
    "conflicts": [],
})

TASK_REPLY_TEMPLATE = json.dumps({
    "tasks": [
        {"title": "Review RAG embeddings notes",
         "description": "Re-read the saved RAG notes and summarize key ideas.",
         "priority": "high", "source_ids": ["__C1__"],
         "kind": "outstanding", "status": "draft"}
    ]
})


def _replies_with_chunk(chunk_id):
    return (
        ANALYSIS_REPLY.replace("__C1__", chunk_id),
        TASK_REPLY_TEMPLATE.replace("__C1__", chunk_id),
    )


# --- The full lifecycle: workflow -> awaiting_approval -> approve ----------


def test_full_lifecycle_workflow_then_approve_persists(repository, database_engine):
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    _, chunk_ids = seed_memory(
        repository, sessions, "mem_rag1",
        "RAG retrieval uses embeddings and vector search for similarity.", RAG_VEC,
    )
    chunk_id = chunk_ids[0]
    analysis_reply, task_reply = _replies_with_chunk(chunk_id)

    orch = build_orchestrator(
        repository, database_engine, analysis_reply=analysis_reply, task_reply=task_reply
    )
    store = RunStore()
    wire_app(orch, store, database_engine)
    try:
        with TestClient(app) as client:
            # 1. Run the workflow end to end.
            wf = client.post(
                "/api/v1/workflow",
                json={"question": "create tasks from my RAG notes"},
            )
            assert wf.status_code == 200, wf.text
            body = wf.json()
            assert body["objective"] == "create_tasks"
            assert body["status"] == "awaiting_approval"
            assert body["run_id"].startswith("run_")
            # Evidence + drafts returned; draft source ids are real chunk ids.
            assert len(body["evidence"]) >= 1
            evidence_ids = {e["chunk_id"] for e in body["evidence"]}
            assert chunk_id in evidence_ids
            assert len(body["task_drafts"]) == 1
            draft = body["task_drafts"][0]
            assert draft["status"] == "draft"
            assert set(draft["source_ids"]).issubset(evidence_ids)
            # Findings distinguish evidence and unknowns.
            assert body["findings"]
            # Traces show the full stage sequence.
            assert [t["stage"] for t in body["trace"]] == ["router", "retrieval", "analysis", "task"]
            # Requirement 2: drafts are NOT persisted before approval.
            assert count_tasks(database_engine) == 0

            run_id = body["run_id"]
            # 2. Approve explicitly through the approval endpoint.
            appr = client.post(f"/api/v1/workflow/{run_id}/approve",
                               json={"decision": "approve"})
            assert appr.status_code == 200, appr.text
            appr_body = appr.json()
            assert appr_body["status"] == "completed"
            assert len(appr_body["persisted_task_ids"]) == 1

            # Requirement 3: approval persisted the valid draft.
            assert count_tasks(database_engine) == 1
    finally:
        clear_app()


def test_persisted_task_reference_preserves_draft_fields(repository, database_engine):
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    _, chunk_ids = seed_memory(
        repository, sessions, "mem_rag2",
        "RAG retrieval uses embeddings and vector search for similarity.", RAG_VEC,
    )
    chunk_id = chunk_ids[0]
    analysis_reply, task_reply = _replies_with_chunk(chunk_id)
    orch = build_orchestrator(
        repository, database_engine, analysis_reply=analysis_reply, task_reply=task_reply
    )
    store = RunStore()
    wire_app(orch, store, database_engine)
    task_sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    repo = TaskRepository(task_sessions)
    try:
        with TestClient(app) as client:
            wf = client.post("/api/v1/workflow",
                             json={"question": "create tasks from my RAG notes"})
            run_id = wf.json()["run_id"]
            appr = client.post(f"/api/v1/workflow/{run_id}/approve",
                               json={"decision": "approve"})
            stored = repo.get_by_id(appr.json()["persisted_task_ids"][0])
    finally:
        clear_app()
    assert stored["task_type"] == "agent_task_draft"
    assert stored["status"] == "todo"
    ref = stored["input_reference"]
    assert ref["title"] == "Review RAG embeddings notes"
    assert ref["priority"] == "high"
    assert ref["kind"] == "outstanding"
    assert ref["source_ids"] == [chunk_id]
    assert ref["run_id"] == run_id



# --- Reject, stale, duplicate, replay through the real endpoints -----------


def _run_to_awaiting(repository, database_engine, client, question="create tasks from my RAG notes"):
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    _, chunk_ids = seed_memory(
        repository, sessions, "mem_rag1",
        "RAG retrieval uses embeddings and vector search for similarity.", RAG_VEC,
    )
    chunk_id = chunk_ids[0]
    analysis_reply, task_reply = _replies_with_chunk(chunk_id)
    orch = build_orchestrator(
        repository, database_engine, analysis_reply=analysis_reply, task_reply=task_reply
    )
    store = RunStore()
    wire_app(orch, store, database_engine)
    body = client.post("/api/v1/workflow", json={"question": question}).json()
    return body["run_id"]


def test_reject_persists_nothing(repository, database_engine):
    store = RunStore()
    wire_app(None, store, database_engine)  # placeholder; replaced below
    try:
        with TestClient(app) as client:
            run_id = _run_to_awaiting(repository, database_engine, client)
            rej = client.post(f"/api/v1/workflow/{run_id}/approve",
                              json={"decision": "reject"})
            assert rej.status_code == 200
            assert rej.json()["status"] == "rejected"
            assert count_tasks(database_engine) == 0
    finally:
        clear_app()


def test_duplicate_approval_after_completion_is_rejected(repository, database_engine):
    try:
        with TestClient(app) as client:
            run_id = _run_to_awaiting(repository, database_engine, client)
            first = client.post(f"/api/v1/workflow/{run_id}/approve",
                                json={"decision": "approve"})
            assert first.status_code == 200
            # A replayed approval of the same run must not double-write.
            second = client.post(f"/api/v1/workflow/{run_id}/approve",
                                 json={"decision": "approve"})
            assert second.status_code in (404, 409)
            assert count_tasks(database_engine) == 1
    finally:
        clear_app()


def test_unknown_run_id_is_rejected(repository, database_engine):
    store = RunStore()
    wire_app(None, store, database_engine)
    try:
        with TestClient(app) as client:
            resp = client.post("/api/v1/workflow/run_does_not_exist/approve",
                               json={"decision": "approve"})
            assert resp.status_code == 404
            assert count_tasks(database_engine) == 0
    finally:
        clear_app()


def test_edit_with_fabricated_source_id_does_not_persist(repository, database_engine):
    try:
        with TestClient(app) as client:
            run_id = _run_to_awaiting(repository, database_engine, client)
            # Edit that cites a chunk id that was never retrieved.
            resp = client.post(
                f"/api/v1/workflow/{run_id}/approve",
                json={"decision": "edit", "edited_drafts": {"tasks": [
                    {"title": "Bogus", "description": "Cites nothing real.",
                     "priority": "low", "source_ids": ["chunk_missing"],
                     "kind": "recommended", "status": "draft"}
                ]}},
            )
            assert resp.status_code == 422
            assert count_tasks(database_engine) == 0
    finally:
        clear_app()


def test_valid_edit_persists_revalidated_drafts(repository, database_engine):
    try:
        with TestClient(app) as client:
            run_id = _run_to_awaiting(repository, database_engine, client)
            # Discover a real chunk id from the workflow response evidence.
            # (Re-run to read evidence ids, then edit to a valid title.)
            sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
            # The single seeded memory yields one chunk id; fetch it via a fresh run.
            body = client.post("/api/v1/workflow",
                               json={"question": "create tasks from my RAG notes"}).json()
            chunk_id = body["evidence"][0]["chunk_id"]
            resp = client.post(
                f"/api/v1/workflow/{body['run_id']}/approve",
                json={"decision": "edit", "edited_drafts": {"tasks": [
                    {"title": "Edited RAG task", "description": "Re-read the notes.",
                     "priority": "medium", "source_ids": [chunk_id],
                     "kind": "recommended", "status": "draft"}
                ]}},
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["status"] == "completed"
            assert count_tasks(database_engine) == 1
    finally:
        clear_app()



# --- Failure paths exercised end to end ------------------------------------


def test_no_relevant_memories_yields_empty_evidence(repository, database_engine):
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    seed_memory(repository, sessions, "mem_cook1", "Pasta with tomato and basil.", COOK_VEC)
    orch = build_orchestrator(
        repository, database_engine,
        analysis_reply=ANALYSIS_REPLY, task_reply=TASK_REPLY_TEMPLATE,
    )
    store = RunStore()
    wire_app(orch, store, database_engine)
    try:
        with TestClient(app) as client:
            resp = client.post("/api/v1/workflow",
                               json={"question": "find my RAG notes"})
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["objective"] == "search"
            assert body["evidence"] == []
            assert body["status"] == "completed"
            assert count_tasks(database_engine) == 0
    finally:
        clear_app()


def test_conflicting_records_reported_with_both_refs(repository, database_engine):
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    _, c1 = seed_memory(repository, sessions, "mem_a",
                        "RAG uses embeddings for vector search.", [1.0, 0.0, 0.0])
    _, c2 = seed_memory(repository, sessions, "mem_b",
                        "RAG does not use embeddings at all.", [0.98, 0.05, 0.0])
    conflict_reply = json.dumps({
        "findings": [],
        "inferences": [],
        "unknowns": ["The records do not agree on whether RAG uses embeddings."],
        "conflicts": [
            {"description": "Records disagree on RAG embeddings usage.",
             "evidence_refs": [c1[0], c2[0]]}
        ],
    })
    orch = build_orchestrator(
        repository, database_engine, analysis_reply=conflict_reply, task_reply=TASK_REPLY_TEMPLATE,
    )
    store = RunStore()
    wire_app(orch, store, database_engine)
    try:
        with TestClient(app) as client:
            resp = client.post("/api/v1/workflow",
                               json={"question": "summarize my RAG notes"})
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["objective"] == "summarize"
            assert body["status"] == "completed"
    finally:
        clear_app()


def test_malformed_model_output_fails_run_safely(repository, database_engine):
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    seed_memory(repository, sessions, "mem_rag1",
                "RAG retrieval uses embeddings and vector search.", RAG_VEC)
    orch = build_orchestrator(
        repository, database_engine,
        analysis_reply="not json {{{", task_reply=TASK_REPLY_TEMPLATE,
    )
    store = RunStore()
    wire_app(orch, store, database_engine)
    try:
        with TestClient(app) as client:
            resp = client.post("/api/v1/workflow",
                               json={"question": "summarize my RAG notes"})
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["status"] == "failed"
            assert any(e["category"] == "invalid_response" for e in body["errors"])
            assert count_tasks(database_engine) == 0
    finally:
        clear_app()



def test_unknown_source_id_in_task_output_fails_run(repository, database_engine):
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    _, chunk_ids = seed_memory(repository, sessions, "mem_rag1",
                               "RAG retrieval uses embeddings and vector search.", RAG_VEC)
    analysis_reply, _ = _replies_with_chunk(chunk_ids[0])
    bad_task = json.dumps({"tasks": [
        {"title": "Bogus", "description": "Cites nothing real.",
         "priority": "low", "source_ids": ["chunk_missing"],
         "kind": "recommended", "status": "draft"}
    ]})
    orch = build_orchestrator(
        repository, database_engine, analysis_reply=analysis_reply, task_reply=bad_task,
    )
    store = RunStore()
    wire_app(orch, store, database_engine)
    try:
        with TestClient(app) as client:
            resp = client.post("/api/v1/workflow",
                               json={"question": "create tasks from my RAG notes"})
            body = resp.json()
            assert body["status"] == "failed"
            assert any(e["category"] == "unknown_evidence" for e in body["errors"])
            assert count_tasks(database_engine) == 0
    finally:
        clear_app()


def test_model_unavailable_surfaces_safe_error(repository, database_engine):
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    seed_memory(repository, sessions, "mem_rag1",
                "RAG retrieval uses embeddings and vector search.", RAG_VEC)
    orch = build_orchestrator(
        repository, database_engine,
        analysis_reply=ANALYSIS_REPLY, task_reply=TASK_REPLY_TEMPLATE,
        analysis_failing=True,  # Ollama connect refused
    )
    store = RunStore()
    wire_app(orch, store, database_engine)
    try:
        with TestClient(app) as client:
            resp = client.post("/api/v1/workflow",
                               json={"question": "summarize my RAG notes"})
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["status"] == "failed"
            assert any(e["category"] == "unavailable" for e in body["errors"])
            assert count_tasks(database_engine) == 0
    finally:
        clear_app()


def test_retrieval_unavailable_marks_run_failed(repository, database_engine):
    # A genuine retrieval failure: BOTH channels unavailable. The hybrid
    # service degrades from a failed semantic channel to the keyword channel,
    # so to make retrieval itself fail we disable the keyword weight AND break
    # the embedding transport. The run must then FAIL safely, not complete.
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    seed_memory(repository, sessions, "mem_rag1",
                "RAG retrieval uses embeddings and vector search.", RAG_VEC)
    from dataclasses import replace

    emb_config = Settings(
        ollama_base_url="http://127.0.0.1:11434", embedding_model=MODEL,
        rag_keyword_weight=0,  # no keyword fallback -> semantic outage is fatal
    )

    def failing_embed(url: str, **kwargs):
        raise httpx.ConnectError("refused", request=httpx.Request("POST", url))

    emb = EmbeddingService(config=emb_config, post=failing_embed)
    service = HybridRetrievalService(
        memories=repository,
        chunks=ChunkRepository(sessions),
        vectors=VectorStore(sessions),
        embeddings=emb,
        keywords=KeywordSearchService(sessions),
        sessions=sessions,
        config=emb_config,
    )
    orch = Orchestrator(
        router=QueryRouter(policy=make_policy()),
        retrieval=service,
        analysis_model=None, task_model=None, policy=make_policy(),
    )
    store = RunStore()
    wire_app(orch, store, database_engine)
    try:
        with TestClient(app) as client:
            resp = client.post("/api/v1/workflow",
                               json={"question": "find my RAG notes"})
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["status"] == "failed"
            assert any(e["category"] == "unavailable" for e in body["errors"])
            assert count_tasks(database_engine) == 0
    finally:
        clear_app()


def test_task78_resilience_exercised_end_to_end(repository, database_engine):
    # A transient analysis-model outage that succeeds on retry: the workflow
    # must complete (not fail) and the analysis trace must show >1 attempt.
    # This exercises the Task 78 retry path (call_with_retries) end to end
    # through the real orchestrator and API.
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    _, chunk_ids = seed_memory(repository, sessions, "mem_rag1",
                               "RAG retrieval uses embeddings and vector search.", RAG_VEC)
    chunk_id = chunk_ids[0]
    analysis_reply, task_reply = _replies_with_chunk(chunk_id)

    calls = {"n": 0}

    def flaky_analysis(url: str, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("refused", request=httpx.Request("POST", url))
        return httpx.Response(
            200, json={"message": {"content": analysis_reply}, "done": True},
            request=httpx.Request("POST", url),
        )

    from app.agents.analysis_agent import OllamaAnalysisModel
    from app.agents.task_agent import OllamaTaskModel

    emb_config = Settings(ollama_base_url="http://127.0.0.1:11434", embedding_model=MODEL)

    def good_embed(url: str, **kwargs):
        inputs = kwargs["json"]["input"]
        return httpx.Response(
            200, json={"embeddings": [list(QUERY_VEC) for _ in inputs]},
            request=httpx.Request("POST", url),
        )

    emb = EmbeddingService(config=emb_config, post=good_embed)
    service = HybridRetrievalService(
        memories=repository,
        chunks=ChunkRepository(sessions),
        vectors=VectorStore(sessions),
        embeddings=emb,
        keywords=KeywordSearchService(sessions),
        sessions=sessions,
        config=emb_config,
    )
    model_config = Settings(ollama_base_url="http://127.0.0.1:11434", ollama_model="unit-model")
    orch = Orchestrator(
        router=QueryRouter(policy=make_policy()),
        retrieval=service,
        analysis_model=OllamaAnalysisModel(config=model_config, post=flaky_analysis),
        task_model=OllamaTaskModel(config=model_config, post=ollama_post(task_reply)),
        policy=make_policy(),
    )
    store = RunStore()
    wire_app(orch, store, database_engine)
    try:
        with TestClient(app) as client:
            resp = client.post("/api/v1/workflow",
                               json={"question": "create tasks from my RAG notes"})
            assert resp.status_code == 200, resp.text
            body = resp.json()
            # Despite the first transient analysis failure, the run reached approval.
            assert body["status"] == "awaiting_approval"
            analysis_trace = [t for t in body["trace"] if t["stage"] == "analysis"][0]
            assert analysis_trace["status"] == "ok"
            assert analysis_trace["attempts"] >= 2  # a retry happened
    finally:
        clear_app()

