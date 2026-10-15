"""Task 92 — cross-boundary integration tests for the backend + database.

Unlike the per-endpoint suites, these tests walk a single memory through the
*real* capture -> persist -> index -> retrieve -> delete lifecycle using the real
FastAPI routes, the real services, and the real (disposable) SQLite database, so
they exercise how those layers actually work together.

Only the model boundary is substituted: embeddings come from a deterministic
fake transport (no network, no model, no credentials), and the database is the
per-test temp SQLite file created by ``conftest``. Nothing here can read, write,
migrate, or delete the personal ``recallai.db``.

Coverage maps to Task 92:
  A. capture + persistence          -> test_*_persists* / test_invalid_payloads*
  B. retrieval + memory lookup      -> test_capture_..._lifecycle / test_ask_unrelated*
  C. memory/source deletion         -> test_delete_..._cascades* / lifecycle step 6-10
  D. workflow execution             -> covered by tests/test_e2e_workflow.py (not duplicated)
  E. MCP integration                -> covered by tests/test_mcp_server.py (not duplicated)
  F. transaction/rollback + cleanup -> conftest temp DB per test; test_invalid_payloads*
"""

from __future__ import annotations

import httpx
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_retrieval_service
from app.core.config import Settings
from app.main import app
from app.repositories.chunk_store import ChunkRepository
from app.repositories.sqlite_store import MemoryRepository
from app.repositories.vector_store import VectorStore
from app.services.chunking import chunk_text
from app.services.embeddings import EmbeddingService
from app.services.hybrid import HybridRetrievalService
from app.services.keyword_search import KeywordSearchService
from tests._factories import browser_payload

MODEL = "unit-embed-model"
RAG_VEC = [1.0, 0.0, 0.0]      # "topic A": embeddings / vector search
COOK_VEC = [0.0, 1.0, 0.0]     # orthogonal "topic B": unrelated (weather)

_TOPIC_A = ("embedding", "vector", "similarity", "hnsw", "index", "memories")
_TOPIC_B = ("weather", "paris", "sunny", "forecast")


def _override(service) -> None:
    app.dependency_overrides[get_retrieval_service] = lambda: service


def _clear_override() -> None:
    # Remove ONLY the retrieval override. Using app.dependency_overrides.clear()
    # would also drop the get_repository override the ``client`` fixture relies
    # on, silently routing later calls (e.g. DELETE) to the real database.
    app.dependency_overrides.pop(get_retrieval_service, None)


def _embed(text: str) -> list[float]:
    """Deterministic 3-D embedding: topic A or an orthogonal topic B vector."""
    lowered = text.lower()
    if any(token in lowered for token in _TOPIC_B):
        return list(COOK_VEC)
    return list(RAG_VEC)


def _service_for(database_engine, **config):
    """The real hybrid retrieval service wired to a deterministic fake embedder.

    The ``post`` transport mirrors the Ollama embeddings endpoint shape but is
    resolved locally, so no model or network is ever contacted.
    """
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)

    def fake_post(url: str, **kwargs):
        inputs = kwargs["json"]["input"]
        return httpx.Response(
            200,
            json={"embeddings": [_embed(t) for t in inputs]},
            request=httpx.Request("POST", url),
        )

    base = Settings(ollama_base_url="http://127.0.0.1:11434", embedding_model=MODEL)
    settings_obj = base.replace(**config) if config else base
    return HybridRetrievalService(
        memories=MemoryRepository(sessions),
        chunks=ChunkRepository(sessions),
        vectors=VectorStore(sessions),
        embeddings=EmbeddingService(config=settings_obj, post=fake_post),
        keywords=KeywordSearchService(sessions),
        sessions=sessions,
        config=settings_obj,
    )


def _index_memory(database_engine, memory_id: str, vector=RAG_VEC) -> None:
    """Index an already-persisted memory exactly as production indexing would:
    chunk its stored text and upsert the vectors. Deterministic, no model."""
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    record = MemoryRepository(sessions).get_by_id(memory_id)
    assert record is not None, "memory must exist before it can be indexed"
    chunk_ids = ChunkRepository(sessions).replace_memory_chunks(
        memory_id, chunk_text(record.normalized_text, memory_id)
    )
    VectorStore(sessions).upsert_many(
        [(cid, memory_id, list(vector)) for cid in chunk_ids], MODEL
    )


def _chunk_count(database_engine, memory_id: str) -> int:
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    return len(ChunkRepository(sessions).get_chunks(memory_id))


def _vector_count(database_engine) -> int:
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    return VectorStore(sessions).count()



# --- A/B/C. Capture -> persist -> index -> retrieve -> delete lifecycle ------


def test_capture_persist_index_retrieve_delete_lifecycle(client, repository, database_engine):
    """One memory travels through the real routes and DB at every stage."""
    # A. Capture through the real ingestion route -> 201 Created, record persisted.
    payload = browser_payload(
        id="mem_lifecycle",
        extractedText="HNSW graphs index embeddings for fast similarity search across memories.",
    )
    created = client.post("/api/v1/ingest/browser", json=payload)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["duplicate"] is False
    assert body["record_id"] == "mem_lifecycle"
    assert body["content_hash"]
    memory_id = body["record_id"]
    assert repository.count() == 1
    assert repository.get_by_id(memory_id) is not None

    # It is listed by the memories API (persistence is observable through the API).
    listing = client.get("/api/v1/memories").json()
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == memory_id

    # Capture the source id now, before deletion, so we can check the count after.
    detail = client.get(f"/api/v1/memories/{memory_id}").json()
    assert detail["source"]["memory_count"] == 1
    source_id = detail["source"]["id"]

    # Index it the way production would (chunk + vector), then retrieve via the
    # real hybrid service with a deterministic fake embedding transport.
    _index_memory(database_engine, memory_id, RAG_VEC)
    _override(_service_for(database_engine))
    try:
        answered = client.post(
            "/api/v1/ask",
            json={"question": "How do vector embeddings enable similarity search?"},
        )
    finally:
        _clear_override()
    assert answered.status_code == 200
    ask_body = answered.json()
    assert ask_body["confidence"] in {"weak", "strong"}
    assert any(item["memory_id"] == memory_id for item in ask_body["evidence"])

    # C. Delete through the real route -> 200, record no longer retrievable.
    deleted = client.delete(f"/api/v1/memories/{memory_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True

    gone = client.get(f"/api/v1/memories/{memory_id}")
    assert gone.status_code == 404

    # B. The deleted memory can never appear in retrieval results again.
    _override(_service_for(database_engine))
    try:
        after = client.post(
            "/api/v1/ask",
            json={"question": "How do vector embeddings enable similarity search?"},
        )
    finally:
        _clear_override()
    assert after.status_code == 200
    assert after.json()["evidence"] == []

    # C. Cascade: chunks and vectors are gone; the source survives with count 0.
    assert repository.get_by_id(memory_id) is None
    assert _chunk_count(database_engine, memory_id) == 0
    assert _vector_count(database_engine) == 0
    source_after = client.get(f"/api/v1/sources/{source_id}")
    assert source_after.status_code == 200
    assert source_after.json()["memory_count"] == 0


def test_delete_cascades_chunks_and_vectors_at_db_boundary(client, repository, database_engine):
    """Database-level ON DELETE CASCADE removes derived chunk/vector rows."""
    created = client.post(
        "/api/v1/ingest/browser",
        json=browser_payload(
            id="mem_cascade",
            extractedText="Similarity search over stored embeddings requires an index.",
        ),
    )
    assert created.status_code == 201
    memory_id = created.json()["record_id"]

    _index_memory(database_engine, memory_id, RAG_VEC)
    assert _chunk_count(database_engine, memory_id) >= 1
    assert _vector_count(database_engine) >= 1

    assert client.delete(f"/api/v1/memories/{memory_id}").status_code == 200

    # FK cascade (PRAGMA foreign_keys=ON is enabled by create_database_engine).
    assert _chunk_count(database_engine, memory_id) == 0
    assert _vector_count(database_engine) == 0


# --- A. Capture idempotency + validation -----------------------------------


def test_duplicate_ingest_is_idempotent_across_api(client, repository):
    """Posting identical content twice creates one row: 201 then 200."""
    payload = browser_payload(
        id="mem_dup",
        extractedText="Duplicate browser captures must deduplicate by content.",
    )
    first = client.post("/api/v1/ingest/browser", json=payload)
    second = client.post("/api/v1/ingest/browser", json=payload)

    assert first.status_code == 201
    assert first.json()["duplicate"] is False
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert first.json()["record_id"] == second.json()["record_id"]
    assert repository.count() == 1


def test_invalid_payloads_leave_no_records(client, repository):
    """Every rejected payload maps to 422 and persists nothing (no partial rows)."""
    invalid_payloads = [
        browser_payload(extractedText="   "),                 # whitespace-only text
        browser_payload(title=""),                            # empty title
        browser_payload(url="ftp://not-http.example/x"),      # non-http url
        browser_payload(domain="other.example"),              # domain != url host
        browser_payload(captureType="selection"),             # selection w/o selectedText
        browser_payload(captureType="selection", selectedText=""),  # empty selection
    ]
    for payload in invalid_payloads:
        response = client.post("/api/v1/ingest/browser", json=payload)
        assert response.status_code == 422, payload

    assert repository.count() == 0


# --- B. Retrieval: unrelated records are not returned -----------------------


def test_ask_unrelated_question_returns_empty_evidence(client, database_engine, repository):
    """An indexed memory is not returned for an orthogonal, unrelated query.

    The fake embedder maps the question to a vector orthogonal to the stored one
    and shares no keywords, so neither retrieval channel matches.
    """
    created = client.post(
        "/api/v1/ingest/browser",
        json=browser_payload(
            id="mem_topic_a",
            extractedText="HNSW graphs index embeddings for fast similarity search.",
        ),
    )
    assert created.status_code == 201
    memory_id = created.json()["record_id"]
    _index_memory(database_engine, memory_id, RAG_VEC)

    _override(_service_for(database_engine))
    try:
        response = client.post(
            "/api/v1/ask",
            json={"question": "What is the weather forecast in Paris this week?"},
        )
    finally:
        _clear_override()

    assert response.status_code == 200
    body = response.json()
    assert body["evidence"] == []
    assert body["confidence"] == "none"
    assert repository.get_by_id(memory_id) is not None  # untouched, just not matched

