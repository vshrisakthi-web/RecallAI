"""Indexing tests — the link between stored memories and the retrieval index.

Every test uses a fake embedding transport, so no model is started and no
network request is made. These tests exist because the index was previously
only ever populated by other tests: ingestion did not chunk or embed anything,
so a real database would have had an empty index and retrieval would have found
nothing.
"""

from __future__ import annotations

from dataclasses import replace

import httpx
import pytest
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.repositories.chunk_store import ChunkRepository
from app.repositories.sqlite_store import MemoryRepository
from app.repositories.vector_store import VectorStore
from app.services.chunking import chunk_text
from app.services.embeddings import EmbeddingService
from app.services.indexing import (
    INDEXED,
    SKIPPED_EMPTY,
    IndexingService,
    IndexingUnavailableError,
)
from tests._factories import make_record

MODEL = "unit-embed-model"


def indexer(database_engine, repository, failing=False, vector=None):
    """The real IndexingService with a fake embedding transport."""
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)

    def fake_post(url: str, **kwargs):
        if failing:
            raise httpx.ConnectError("refused", request=httpx.Request("POST", url))
        inputs = kwargs["json"]["input"]
        values = vector or [1.0, 0.0, 0.0]
        return httpx.Response(
            200,
            json={"embeddings": [list(values) for _ in inputs]},
            request=httpx.Request("POST", url),
        )

    config = Settings(ollama_base_url="http://127.0.0.1:11434", embedding_model=MODEL)
    return (
        IndexingService(
            memories=repository,
            chunks=ChunkRepository(sessions),
            vectors=VectorStore(sessions),
            embeddings=EmbeddingService(config=config, post=fake_post),
            config=config,
        ),
        sessions,
    )


def save(repository, memory_id, text="HNSW graphs index embeddings for similarity search."):
    saved, _ = repository.save_or_get(make_record(id=memory_id, _text=text))
    return saved


def chunk_without_embedding(repository, sessions, memory_id):
    """Simulate a database whose chunks exist but were never embedded."""
    record = repository.get_by_id(memory_id)
    return ChunkRepository(sessions).replace_memory_chunks(
        memory_id, chunk_text(record.normalized_text, memory_id)
    )


# --- Indexing one memory --------------------------------------------------


def test_indexing_creates_chunks_and_vectors(repository, database_engine):
    service, sessions = indexer(database_engine, repository)
    save(repository, "mem_a")

    outcome = service.index_memory("mem_a")

    assert outcome.indexed
    assert outcome.status == INDEXED
    assert outcome.chunk_count >= 1
    assert ChunkRepository(sessions).count_chunks("mem_a") == outcome.chunk_count
    assert VectorStore(sessions).count(MODEL) == outcome.chunk_count


def test_indexing_is_idempotent_for_unchanged_content(repository, database_engine):
    """Re-running must replace rows, not duplicate them."""
    service, sessions = indexer(database_engine, repository)
    save(repository, "mem_a")

    first = service.index_memory("mem_a")
    ids_first = [c.id for c in ChunkRepository(sessions).get_chunks("mem_a")]
    second = service.index_memory("mem_a")
    ids_second = [c.id for c in ChunkRepository(sessions).get_chunks("mem_a")]

    assert first.chunk_count == second.chunk_count
    assert ids_first == ids_second  # stable, content-derived ids
    assert ChunkRepository(sessions).count_chunks("mem_a") == second.chunk_count
    assert VectorStore(sessions).count(MODEL) == second.chunk_count


def test_indexing_empty_text_is_skipped_not_an_error(repository, database_engine):
    service, sessions = indexer(database_engine, repository)
    save(repository, "mem_empty", text="   ")

    outcome = service.index_memory("mem_empty")

    assert outcome.status == SKIPPED_EMPTY
    assert not outcome.indexed
    assert ChunkRepository(sessions).count_chunks("mem_empty") == 0


def test_indexing_a_missing_memory_raises(repository, database_engine):
    service, _ = indexer(database_engine, repository)
    with pytest.raises(IndexingUnavailableError):
        service.index_memory("mem_does_not_exist")


def test_embedding_failure_leaves_no_partial_index(repository, database_engine):
    """A failed embed must not leave orphaned chunks behind."""
    service, sessions = indexer(database_engine, repository, failing=True)
    save(repository, "mem_a")

    with pytest.raises(IndexingUnavailableError):
        service.index_memory("mem_a")

    assert ChunkRepository(sessions).count_chunks("mem_a") == 0
    assert VectorStore(sessions).count() == 0


def test_remove_memory_drops_its_chunks_and_vectors(repository, database_engine):
    service, sessions = indexer(database_engine, repository)
    save(repository, "mem_a")
    service.index_memory("mem_a")
    assert VectorStore(sessions).count(MODEL) > 0

    assert service.remove_memory("mem_a") >= 1

    assert ChunkRepository(sessions).count_chunks("mem_a") == 0
    assert VectorStore(sessions).count() == 0  # cascade


# --- Sweeping pending memories -------------------------------------------


def test_sweep_indexes_unindexed_memories(repository, database_engine):
    """The path that brings an existing database up to date."""
    service, sessions = indexer(database_engine, repository)
    save(repository, "mem_b", "HNSW graphs index embeddings for search.")
    save(repository, "mem_a", "IVF lists partition embeddings for lookup.")
    # Simulate chunks that exist but were never embedded.
    chunk_without_embedding(repository, sessions, "mem_a")
    chunk_without_embedding(repository, sessions, "mem_b")
    assert VectorStore(sessions).count() == 0

    outcomes = service.index_pending_memories()

    assert len(outcomes) == 2
    assert all(o.indexed for o in outcomes)
    assert VectorStore(sessions).count(MODEL) > 0


def test_sweep_is_a_noop_when_everything_is_indexed(repository, database_engine):
    service, sessions = indexer(database_engine, repository)
    save(repository, "mem_a")
    service.index_memory("mem_a")

    assert service.index_pending_memories() == []


def test_sweep_reports_and_stops_when_the_model_is_unreachable(repository, database_engine):
    service, sessions = indexer(database_engine, repository, failing=True)
    save(repository, "mem_a")
    chunk_without_embedding(repository, sessions, "mem_a")

    outcomes = service.index_pending_memories()

    assert len(outcomes) == 1
    assert not outcomes[0].indexed
    assert outcomes[0].detail
    assert VectorStore(sessions).count() == 0

