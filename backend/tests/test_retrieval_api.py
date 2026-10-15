"""Task 6.6 — endpoint tests for POST /api/v1/ask.

The retrieval boundary is always substituted with a fake service (or the real
one wired to a fake embedding transport), so these tests never start a model,
never perform a network request, and never need credentials. They cover the
success/empty/error shapes, the error envelope and request-id conventions, and
the privacy rule that the question is never logged.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_retrieval_service
from app.core.config import Settings
from app.main import app
from app.repositories.chunk_store import ChunkRepository
from app.repositories.sqlite_store import MemoryRepository
from app.repositories.vector_store import VectorStore
from app.services.chunking import chunk_text
from app.services.embeddings import EmbeddingService
from app.services.evidence import RetrievalInputError, RetrievalResult, RetrievalUnavailableError
from app.services.hybrid import HybridRetrievalService
from app.services.keyword_search import KeywordSearchService
from app.services.temporal import normalize_and_parse
from tests._factories import make_record, utcnow

MODEL = "unit-embed-model"
RAG_VEC = [1.0, 0.05, 0.0]
COOK_VEC = [0.0, 1.0, 0.0]


class _FakeRetrieval:
    """Stands in for the retrieval service; records the arguments it was given."""

    def __init__(self, result=None, error=None):
        self.calls: list[str] = []
        self.from_dates: list = []
        self.to_dates: list = []
        self._error = error
        self._result = result

    def retrieve(self, question, top_k=None, from_date=None, to_date=None):
        self.calls.append(question)
        self.from_dates.append(from_date)
        self.to_dates.append(to_date)
        if self._error is not None:
            raise self._error
        return self._result


def _override(service) -> None:
    app.dependency_overrides[get_retrieval_service] = lambda: service


def _clear_override() -> None:
    app.dependency_overrides.clear()


def _result(question="unrelated", evidence=(), candidates=0, temporal=None, channels=("semantic", "keyword")):
    return RetrievalResult(
        query=normalize_and_parse(question, datetime.now(timezone.utc)),
        evidence=list(evidence),
        candidates_considered=candidates,
        temporal=temporal,
        channels=channels,
    )


def _real_service(database_engine, failing=False, vector=RAG_VEC, **config):
    """The real hybrid service with a fake embedding transport."""
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)

    def fake_post(url: str, **kwargs):
        if failing:
            raise httpx.ConnectError("refused", request=httpx.Request("POST", url))
        inputs = kwargs["json"]["input"]
        return httpx.Response(
            200,
            json={"embeddings": [list(vector) for _ in inputs]},
            request=httpx.Request("POST", url),
        )

    base = Settings(ollama_base_url="http://127.0.0.1:11434", embedding_model=MODEL)
    settings_obj = replace(base, **config) if config else base
    return HybridRetrievalService(
        memories=MemoryRepository(sessions),
        chunks=ChunkRepository(sessions),
        vectors=VectorStore(sessions),
        embeddings=EmbeddingService(config=settings_obj, post=fake_post),
        keywords=KeywordSearchService(sessions),
        sessions=sessions,
        config=settings_obj,
    )


def _index(database_engine, repository, memory_id, body, vector=RAG_VEC, title="HNSW embeddings"):
    """Index a memory the way production would: chunk it and store vectors."""
    saved, _ = repository.save_or_get(
        make_record(
            id=memory_id,
            _text=body,
            title=title,
            captured_at=utcnow(),
            source_url="https://example.com/hnsw",
            domain="example.com",
        )
    )
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    chunk_ids = ChunkRepository(sessions).replace_memory_chunks(
        saved.id, chunk_text(saved.normalized_text, saved.id)
    )
    VectorStore(sessions).upsert_many([(cid, saved.id, list(vector)) for cid in chunk_ids], MODEL)


# --- Success and response contract ----------------------------------------


def test_ask_returns_grounded_evidence(client, repository, database_engine):
    _index(database_engine, repository, "mem_a", "HNSW graphs index embeddings for search.")
    _override(_real_service(database_engine))
    try:
        response = client.post("/api/v1/ask", json={"question": "How do HNSW graphs index embeddings?"})
    finally:
        _clear_override()

    assert response.status_code == 200
    body = response.json()
    assert body["confidence"] in {"weak", "strong"}
    assert len(body["evidence"]) >= 1
    item = body["evidence"][0]
    assert item["memory_id"] == "mem_a"
    assert item["chunk_id"].startswith("chk_")
    assert item["passage"]
    assert item["source_title"] == "HNSW embeddings"
    assert item["source_url"] == "https://example.com/hnsw"
    assert item["domain"] == "example.com"
    assert item["captured_at"]
    # Retrieval returns evidence, never a generated answer.
    assert "answer" not in body
    assert set(body["channels"]) == {"semantic", "keyword"}
    assert body["request_id"]


def test_ask_echoes_the_question_verbatim(client, repository, database_engine):
    _index(database_engine, repository, "mem_a", "HNSW graphs index embeddings for search.")
    _override(_real_service(database_engine))
    try:
        body = client.post(
            "/api/v1/ask", json={"question": "  How do HNSW graphs index embeddings?  "}
        ).json()
    finally:
        _clear_override()
    assert body["question"] == "  How do HNSW graphs index embeddings?  "


def test_ask_reports_the_parsed_temporal_window(client, repository, database_engine):
    _override(_real_service(database_engine))
    try:
        body = client.post("/api/v1/ask", json={"question": "what did I save last week?"}).json()
    finally:
        _clear_override()
    assert body["temporal_expression"] == "last week"
    assert body["temporal_from"] and body["temporal_to"]


def test_explicit_date_filters_reach_the_service(client):
    """from_date/to_date on the request are applied, not silently dropped."""
    from datetime import date

    fake = _FakeRetrieval(result=_result())
    _override(fake)
    try:
        response = client.post(
            "/api/v1/ask",
            json={
                "question": "anything",
                "from_date": "2026-10-01",
                "to_date": "2026-10-11",
            },
        )
    finally:
        _clear_override()

    assert response.status_code == 200
    assert fake.from_dates == [date(2026, 10, 1)]
    assert fake.to_dates == [date(2026, 10, 11)]


def test_no_date_filters_sent_as_none(client):
    fake = _FakeRetrieval(result=_result())
    _override(fake)
    try:
        response = client.post("/api/v1/ask", json={"question": "anything"})
    finally:
        _clear_override()

    assert response.status_code == 200
    assert fake.from_dates == [None]
    assert fake.to_dates == [None]


def test_inverted_date_range_maps_to_422(client, repository, database_engine):
    """from_date after to_date is a client error, reported like the list API."""
    _override(_real_service(database_engine))
    try:
        response = client.post(
            "/api/v1/ask",
            json={
                "question": "anything",
                "from_date": "2026-10-11",
                "to_date": "2026-10-01",
            },
        )
    finally:
        _clear_override()

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_ask_returns_request_id_header(client, repository, database_engine):
    _override(_real_service(database_engine))
    try:
        response = client.post("/api/v1/ask", json={"question": "anything at all"})
    finally:
        _clear_override()
    assert response.headers.get("X-Request-ID")


# --- Empty results (a successful search that found nothing) ---------------


def test_no_matches_returns_200_with_empty_evidence(client):
    """Not found is a valid outcome, not an error."""
    _override(_FakeRetrieval(result=_result()))
    try:
        response = client.post(
            "/api/v1/ask", json={"question": "completely unrelated topic"}
        )
    finally:
        _clear_override()

    assert response.status_code == 200
    body = response.json()
    assert body["evidence"] == []
    assert body["confidence"] == "none"


# --- Validation and error mapping -----------------------------------------


def test_empty_question_is_rejected_with_422(client):
    response = client.post("/api/v1/ask", json={"question": ""})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["request_id"]


def test_missing_question_field_is_rejected_with_422(client):
    response = client.post("/api/v1/ask", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_oversized_question_is_rejected_with_422(client):
    response = client.post("/api/v1/ask", json={"question": "x" * 5000})
    assert response.status_code == 422


def test_client_supplied_api_key_is_ignored(client):
    """The endpoint accepts no credentials; a stray field must not be honoured."""
    fake = _FakeRetrieval(result=_result())
    _override(fake)
    try:
        response = client.post(
            "/api/v1/ask",
            json={"question": "anything", "api_key": "sk-should-be-ignored"},
        )
    finally:
        _clear_override()
    assert response.status_code == 200
    assert "sk-should-be-ignored" not in response.text


def test_provider_unavailable_maps_to_503(client):
    _override(_FakeRetrieval(error=RetrievalUnavailableError("model down")))
    try:
        response = client.post("/api/v1/ask", json={"question": "anything"})
    finally:
        _clear_override()

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "PROVIDER_NOT_CONFIGURED"
    assert body["error"]["request_id"]
    # The internal message must not leak to the client.
    assert "model down" not in response.text


def test_service_input_error_maps_to_422(client):
    _override(_FakeRetrieval(error=RetrievalInputError("bad question")))
    try:
        response = client.post("/api/v1/ask", json={"question": "anything"})
    finally:
        _clear_override()

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_embedding_outage_through_the_real_service_maps_to_503(client, repository, database_engine):
    _override(_real_service(database_engine, failing=True, rag_keyword_weight=0.0))
    try:
        response = client.post("/api/v1/ask", json={"question": "anything at all"})
    finally:
        _clear_override()

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PROVIDER_NOT_CONFIGURED"


# --- Privacy --------------------------------------------------------------


def test_question_text_is_never_logged(client, monkeypatch):
    """Only the question's length and the outcome may be logged.

    The route's logger is replaced with a recording stub rather than relying on
    the stdlib handler/propagation machinery, which TestClient's lifespan
    reconfigures. That makes the assertion about *what the route logs*
    deterministic.
    """
    from app.api.routes import retrieval as retrieval_route

    secret = "my-private-question-about-a-secret-topic"

    class _RecordingLogger:
        def __init__(self):
            self.records: list[tuple[str, tuple, dict]] = []

        def info(self, message, *args, **kwargs):
            self.records.append((message, args, kwargs))

        def warning(self, message, *args, **kwargs):
            self.records.append((message, args, kwargs))

    recorder = _RecordingLogger()
    monkeypatch.setattr(retrieval_route, "logger", recorder)
    _override(_FakeRetrieval(result=_result()))
    try:
        response = client.post("/api/v1/ask", json={"question": secret})
    finally:
        _clear_override()

    assert response.status_code == 200
    assert recorder.records, "the outcome should be logged for observability"
    for message, args, _kwargs in recorder.records:
        rendered = message % args if args else message
        assert secret not in rendered
        assert "question length=" in rendered


def test_deleted_memory_never_appears_in_evidence(client, repository, database_engine):
    _index(database_engine, repository, "mem_gone", "HNSW graphs index embeddings for search.")
    assert repository.delete_by_id("mem_gone") is True
    _override(_real_service(database_engine))
    try:
        response = client.post(
            "/api/v1/ask", json={"question": "How do HNSW graphs index embeddings?"}
        )
    finally:
        _clear_override()

    assert response.status_code == 200
    assert response.json()["evidence"] == []


# --- Regression: earlier endpoints still work -----------------------------


def test_memory_endpoints_still_work_alongside_ask(client):
    listing = client.get("/api/v1/memories")
    assert listing.status_code == 200
    health = client.get("/api/v1/health")
    assert health.status_code == 200


