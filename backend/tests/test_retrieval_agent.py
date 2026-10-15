"""Retrieval Agent tests (Module 8, Task 73).

Part 1: helpers, known-record retrieval, empty results, policy bounds.
Uses the real HybridRetrievalService with a fake embedding transport
(same pattern as test_hybrid_retrieval.py) -- fully offline.
"""

from __future__ import annotations

from dataclasses import replace

import httpx
import pytest
from sqlalchemy.orm import sessionmaker

from app.agents.policies import HarnessPolicy
from app.agents.retrieval_agent import run_retrieval
from app.agents.routes import QueryRouter
from app.agents.state import Objective, TraceStatus, WorkflowState, WorkflowRequestError
from app.core.config import Settings
from app.repositories.base import StorageError
from app.repositories.chunk_store import ChunkRepository
from app.repositories.vector_store import VectorStore
from app.services.chunking import chunk_text
from app.services.embeddings import EmbeddingService
from app.services.evidence import (
    Evidence,
    RetrievalInputError,
    RetrievalResult,
    RetrievalUnavailableError,
)
from app.services.temporal import NormalizedQuery
from app.services.hybrid import HybridRetrievalService
from app.services.keyword_search import KeywordSearchService
from tests._factories import make_record, utcnow

MODEL = "unit-embed-model"
RAG_VEC = [1.0, 0.05, 0.0]
COOK_VEC = [0.0, 1.0, 0.0]
QUERY_VEC = [0.95, 0.1, 0.0]


def make_policy(**overrides) -> HarnessPolicy:
    base = dict(
        max_query_chars=200,
        max_evidence_items=4,
        max_evidence_chars=400,
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


def make_state(query="Find my RAG notes", objective=Objective.SEARCH, policy=None):
    state = WorkflowState.create(query, policy or make_policy())
    state.set_objective(objective)
    return state


def make_embeddings(vector, model=MODEL, failing=False):
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


def make_service(repository, database_engine, vector=QUERY_VEC, **config):
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    embeddings, base = make_embeddings(vector)
    settings_obj = replace(base, **config) if config else base
    service = HybridRetrievalService(
        memories=repository,
        chunks=ChunkRepository(sessions),
        vectors=VectorStore(sessions),
        embeddings=embeddings,
        keywords=KeywordSearchService(sessions),
        sessions=sessions,
        config=settings_obj,
    )
    return service, sessions


def seed(repository, sessions, memory_id, text, vector, **kwargs):
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


def test_known_records_return_expected_evidence(repository, database_engine):
    service, sessions = make_service(repository, database_engine)
    seed(repository, sessions, "mem_rag1", "RAG retrieval uses embeddings and vector search.", RAG_VEC)
    seed(repository, sessions, "mem_cook1", "Pasta recipes with tomato and basil.", COOK_VEC)
    state = make_state("Find my RAG notes")
    run_retrieval(state, service)
    assert len(state.evidence) >= 1
    assert state.evidence[0].memory_id == "mem_rag1"
    assert "embeddings" in state.evidence[0].passage
    assert state.trace[-1].stage == "retrieval"
    assert state.trace[-1].status is TraceStatus.OK


def test_empty_index_yields_empty_evidence_with_ok_trace(repository, database_engine):
    service, _sessions = make_service(repository, database_engine)
    state = make_state("Find my RAG notes")
    run_retrieval(state, service)
    assert state.evidence == []
    assert state.errors == []
    assert state.trace[-1].status is TraceStatus.OK


def test_item_budget_truncates_to_policy_cap(repository, database_engine):
    service, sessions = make_service(repository, database_engine)
    for i in range(6):
        seed(repository, sessions, f"mem_rag{i}", f"RAG note number {i} about embeddings.", RAG_VEC)
    state = make_state(policy=make_policy(max_evidence_items=2, max_evidence_chars=10000))
    state.set_objective(Objective.SEARCH)
    run_retrieval(state, service)
    assert len(state.evidence) <= 2


def test_char_budget_drops_trailing_whole_passages():
    policy = make_policy(max_evidence_items=10, max_evidence_chars=20)
    state = make_state(policy=policy)

    def ev(cid, passage):
        return Evidence(
            chunk_id=cid, memory_id="m1", passage=passage,
            source_id=None, source_type=None, source_title=None,
            source_url=None, domain=None, captured_at=None,
            similarity=0.9, score=1.0,
        )

    class StubService:
        def retrieve(self, query, top_k=None):
            return RetrievalResult(
                query=NormalizedQuery(original=query, text=query, temporal=None),
                evidence=[ev("c1", "1234567890"), ev("c2", "abcdefghij"), ev("c3", "EXTRA")],
                candidates_considered=3,
                temporal=None,
                channels=("semantic",),
            )

    run_retrieval(state, StubService())
    assert [e.chunk_id for e in state.evidence] == ["c1", "c2"]
    assert state.evidence[1].passage == "abcdefghij"


def test_duplicate_chunk_ids_collapse_keep_first():
    state = make_state()

    def ev(cid, passage):
        return Evidence(
            chunk_id=cid, memory_id="m1", passage=passage,
            source_id=None, source_type=None, source_title=None,
            source_url=None, domain=None, captured_at=None,
            similarity=0.9, score=1.0,
        )

    class StubService:
        def retrieve(self, query, top_k=None):
            return RetrievalResult(
                query=NormalizedQuery(original=query, text=query, temporal=None),
                evidence=[ev("dup", "same"), ev("dup", "same"), ev("other", "other")],
                candidates_considered=3,
                temporal=None,
                channels=("semantic",),
            )

    run_retrieval(state, StubService())
    assert [e.chunk_id for e in state.evidence] == ["dup", "other"]


def test_unavailable_service_records_safe_error_and_propagates():
    state = make_state()

    class FailingService:
        def retrieve(self, query, top_k=None):
            raise RetrievalUnavailableError("embedding model down")

    with pytest.raises(RetrievalUnavailableError):
        run_retrieval(state, FailingService())
    assert len(state.errors) == 1
    assert state.errors[0].stage == "retrieval"
    assert state.errors[0].category == "unavailable"
    assert "embedding model down" not in state.errors[0].message
    assert state.evidence == []
    assert state.trace[-1].status is TraceStatus.ERROR
    assert state.trace[-1].error_category == "unavailable"


def test_storage_error_records_safe_error_and_propagates():
    state = make_state()

    class BrokenService:
        def retrieve(self, query, top_k=None):
            raise StorageError("disk gone")

    with pytest.raises(StorageError):
        run_retrieval(state, BrokenService())
    assert state.errors[-1].category == "unavailable"
    assert state.trace[-1].status is TraceStatus.ERROR


def test_invalid_input_becomes_workflow_request_error():
    state = make_state()

    class BadInputService:
        def retrieve(self, query, top_k=None):
            raise RetrievalInputError("empty question")

    with pytest.raises(WorkflowRequestError):
        run_retrieval(state, BadInputService())
    assert state.trace[-1].status is TraceStatus.ERROR
    assert state.trace[-1].error_category == "invalid_input"


def test_missing_objective_raises_before_service_called():
    state = WorkflowState.create("Find my notes", make_policy())
    calls = []

    class SpyService:
        def retrieve(self, query, top_k=None):
            calls.append(query)
            raise AssertionError("service must not be called")

    with pytest.raises(Exception):
        run_retrieval(state, SpyService())
    assert calls == []
    assert state.evidence == []
    assert state.trace == []


def test_returned_ids_come_from_service_results():
    state = make_state()
    item = Evidence(
        chunk_id="c9", memory_id="m9", passage="real passage",
        source_id="s9", source_type="note", source_title="t",
        source_url=None, domain=None, captured_at=None,
        similarity=0.9, score=1.0,
    )

    class StubService:
        def retrieve(self, query, top_k=None):
            return RetrievalResult(
                query=NormalizedQuery(original=query, text=query, temporal=None),
                evidence=[item],
                candidates_considered=1,
                temporal=None,
                channels=("semantic",),
            )

    run_retrieval(state, StubService())
    assert state.evidence[0].memory_id == "m9"
    assert state.evidence[0].chunk_id == "c9"
    assert state.evidence[0].source_id == "s9"


def test_top_k_bounds_and_clamps_to_policy():
    seen = {}

    class SpyService:
        def retrieve(self, query, top_k=None):
            seen["top_k"] = top_k
            return RetrievalResult(
                query=NormalizedQuery(original=query, text=query, temporal=None),
                evidence=[],
                candidates_considered=0,
                temporal=None,
                channels=("semantic",),
            )

    run_retrieval(make_state(), SpyService(), top_k=2)
    assert seen["top_k"] == 2
    run_retrieval(make_state(policy=make_policy(max_evidence_items=3)), SpyService(), top_k=50)
    assert seen["top_k"] == 3


def test_router_to_retrieval_handoff():
    router = QueryRouter(policy=make_policy(max_query_chars=200))
    policy = make_policy(max_query_chars=200)
    state = WorkflowState.create("Find my RAG notes", policy)
    router.apply_to_state(state, "Find my RAG notes")
    assert state.objective is Objective.SEARCH

    class StubService:
        def retrieve(self, query, top_k=None):
            assert query == "Find my RAG notes"
            return RetrievalResult(
                query=NormalizedQuery(original=query, text=query, temporal=None),
                evidence=[],
                candidates_considered=0,
                temporal=None,
                channels=("semantic",),
            )

    run_retrieval(state, StubService())
    assert state.evidence == []
    assert [t.stage for t in state.trace] == ["router", "retrieval"]
