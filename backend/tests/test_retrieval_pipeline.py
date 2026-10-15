"""End-to-end pipeline test: capture → ingest → chunk → embed → retrieve.

This is the test that proves the whole Module 6 data flow is genuinely wired,
not just present as files. Before ``IndexingService`` existed, ingestion never
chunked or embedded anything, so a real database had an empty index and
retrieval found nothing — the pieces were correct but unconnected.

Fully offline: the embedding model is a fake transport returning fixed vectors.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_indexing_service, get_retrieval_service
from app.core.config import Settings
from app.main import app
from app.repositories.chunk_store import ChunkRepository
from app.repositories.vector_store import VectorStore
from app.services.embeddings import EmbeddingService
from app.services.hybrid import HybridRetrievalService
from app.services.indexing import IndexingService
from app.services.keyword_search import KeywordSearchService

MODEL = "unit-embed-model"


def _fake_transport(vector):
    def fake_post(url: str, **kwargs):
        inputs = kwargs["json"]["input"]
        return httpx.Response(
            200,
            json={"embeddings": [list(vector) for _ in inputs]},
            request=httpx.Request("POST", url),
        )

    return fake_post


@pytest.fixture()
def wired(client, repository, database_engine):
    """Wire the real indexing and retrieval services onto the test client."""
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    config = Settings(ollama_base_url="http://127.0.0.1:11434", embedding_model=MODEL)
    embeddings = EmbeddingService(config=config, post=_fake_transport([1.0, 0.05, 0.0]))

    app.dependency_overrides[get_indexing_service] = lambda: IndexingService(
        memories=repository,
        chunks=ChunkRepository(sessions),
        vectors=VectorStore(sessions),
        embeddings=embeddings,
        config=config,
    )
    app.dependency_overrides[get_retrieval_service] = lambda: HybridRetrievalService(
        memories=repository,
        chunks=ChunkRepository(sessions),
        vectors=VectorStore(sessions),
        embeddings=embeddings,
        keywords=KeywordSearchService(sessions),
        sessions=sessions,
        config=config,
    )
    yield client, repository, sessions
    app.dependency_overrides.clear()


def _capture(client, memory_id, body):
    response = client.post(
        "/api/v1/ingest/browser",
        json={
            "id": memory_id,
            "title": "HNSW embeddings",
            "url": "https://example.com/hnsw",
            "domain": "example.com",
            "capturedAt": "2026-10-10T09:00:00Z",
            "captureType": "full-page",
            "extractedText": body,
            "status": "ok",
        },
    )
    assert response.status_code == 201
    return response.json()["record_id"]


def test_capture_ingest_index_retrieve_round_trip(wired):
    """The full pipeline, through the real HTTP endpoints."""
    client, repository, sessions = wired
    memory_id = _capture(
        client, "e2e-page", "HNSW graphs index embeddings for similarity search."
    )

    # 1. Ingestion stored the memory but did not index it.
    assert repository.get_by_id(memory_id) is not None
    assert ChunkRepository(sessions).count_chunks(memory_id) == 0

    # 2. Retrieval before indexing finds nothing (the index is empty).
    empty = client.post("/api/v1/ask", json={"question": "How do HNSW graphs work?"})
    assert empty.status_code == 200
    assert empty.json()["evidence"] == []

    # 3. Indexing builds chunks and vectors.
    indexed = client.post(f"/api/v1/memories/{memory_id}/index")
    assert indexed.status_code == 200
    body = indexed.json()
    assert body["status"] == "indexed"
    assert body["chunk_count"] >= 1
    assert ChunkRepository(sessions).count_chunks(memory_id) == body["chunk_count"]

    # 4. Retrieval now returns grounded evidence traced to the stored record.
    payload = client.post(
        "/api/v1/ask", json={"question": "How do HNSW graphs work?"}
    ).json()
    assert payload["evidence"], payload
    item = payload["evidence"][0]
    assert item["memory_id"] == memory_id
    assert item["source_title"] == "HNSW embeddings"
    assert item["source_url"] == "https://example.com/hnsw"
    assert item["chunk_id"].startswith("chk_")
    assert payload["confidence"] in {"weak", "strong"}
    assert "answer" not in payload  # retrieval returns evidence, not prose


def test_sweep_endpoint_indexes_an_existing_database(wired):
    """POST /api/v1/index brings legacy memories up to date."""
    client, _repository, sessions = wired
    _capture(client, "legacy-1", "HNSW graphs index embeddings for similarity search.")
    _capture(client, "legacy-2", "IVF lists partition embeddings for faster lookup.")

    body = client.post("/api/v1/index").json()

    assert body["indexed"] == 2
    assert body["skipped"] == 0
    assert VectorStore(sessions).count(MODEL) >= 2


def test_indexing_a_missing_memory_returns_404(wired):
    client, _repository, _sessions = wired
    response = client.post("/api/v1/memories/does-not-exist/index")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_deleting_a_memory_removes_it_from_retrieval(wired):
    """Deleted memories cannot appear in evidence, end to end."""
    client, _repository, _sessions = wired
    memory_id = _capture(
        client, "e2e-gone", "HNSW graphs index embeddings for similarity search."
    )
    client.post(f"/api/v1/memories/{memory_id}/index")
    assert client.post(
        "/api/v1/ask", json={"question": "How do HNSW graphs work?"}
    ).json()["evidence"]

    assert client.delete(f"/api/v1/memories/{memory_id}").status_code == 200

    after = client.post("/api/v1/ask", json={"question": "How do HNSW graphs work?"})
    assert after.status_code == 200
    assert after.json()["evidence"] == []

