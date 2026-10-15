"""Task 6.3 — embedding persistence and similarity-search tests.

Covers vector-math edge cases (packing, zero-norm, clamping), persistence
across sessions (close/reopen the engine), similarity ranking with known
vectors, idempotent upserts, chunk/memory deletion, stale-model detection,
corrupt-blob tolerance, and the no-raw-vectors guarantee.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import sessionmaker

from app.repositories.base import StorageError
from app.repositories.chunk_store import ChunkRepository
from app.repositories.vector_store import VectorStore
from app.services.chunking import chunk_text
from app.services.vectors import (
    cosine_similarity,
    pack_vector,
    unpack_vector,
)
from tests._factories import make_record


def _save(repository, **overrides):
    record = make_record(**overrides)
    saved, _ = repository.save_or_get(record)
    return saved


def _make_store(database_engine) -> VectorStore:
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    return VectorStore(sessions)


def _indexed(repository, database_engine, memory_id: str, text: str):
    """Chunk one memory's text and return its chunk ids."""
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    return ChunkRepository(sessions).replace_memory_chunks(
        memory_id, chunk_text(text, memory_id)
    )


# --- Vector math -------------------------------------------------------------


def test_pack_unpack_round_trip():
    vector = [0.5, -1.25, 3.0]
    assert unpack_vector(pack_vector(vector), 3) == pytest.approx(vector)


def test_unpack_rejects_truncated_or_mismatched_blobs():
    with pytest.raises(ValueError):
        unpack_vector(b"\x00" * 8, 3)
    with pytest.raises(ValueError):
        unpack_vector(pack_vector([1.0, 2.0]), 3)


def test_cosine_similarity_known_values():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)
    # Zero-norm vectors score 0.0 instead of NaN.
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0
    with pytest.raises(ValueError):
        cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0])


# --- Persistence -------------------------------------------------------------


def test_upsert_and_get_persist_vector(repository, database_engine):
    saved = _save(repository, id="mem_vec", _text="Vector persistence note.")
    (chunk_id,) = _indexed(repository, database_engine, saved.id, "note text")
    store = _make_store(database_engine)

    store.upsert(chunk_id, saved.id, [0.1, 0.2, 0.7], "unit-model")

    row = store.get(chunk_id)
    assert row is not None
    assert row.memory_id == saved.id
    assert row.model == "unit-model"
    assert row.dims == 3
    assert unpack_vector(row.vector, row.dims) == pytest.approx([0.1, 0.2, 0.7])


def test_persistence_survives_engine_reopen(repository, database_engine):
    saved = _save(repository, id="mem_restart", _text="Restart persistence.")
    (chunk_id,) = _indexed(repository, database_engine, saved.id, "note text")
    store = _make_store(database_engine)
    store.upsert(chunk_id, saved.id, [1.0, 0.0], "unit-model")

    database_engine.dispose()
    reopened = _make_store(database_engine)

    row = reopened.get(chunk_id)
    assert row is not None and row.model == "unit-model"


def test_upsert_is_idempotent_and_replaces(repository, database_engine):
    saved = _save(repository, id="mem_dup", _text="Duplicate indexing note.")
    (chunk_id,) = _indexed(repository, database_engine, saved.id, "note text")
    store = _make_store(database_engine)

    store.upsert(chunk_id, saved.id, [1.0, 0.0], "unit-model")
    store.upsert(chunk_id, saved.id, [0.0, 1.0], "unit-model")

    assert store.count() == 1
    row = store.get(chunk_id)
    assert row is not None
    assert unpack_vector(row.vector, row.dims) == pytest.approx([0.0, 1.0])


def test_upsert_many_stores_batches(repository, database_engine):
    first = _save(repository, id="mem_b1", _text="Batch one.")
    second = _save(repository, id="mem_b2", _text="Batch two.")
    (chunk_one,) = _indexed(repository, database_engine, first.id, "one")
    (chunk_two,) = _indexed(repository, database_engine, second.id, "two")
    store = _make_store(database_engine)

    stored = store.upsert_many(
        [(chunk_one, first.id, [1.0, 0.0]), (chunk_two, second.id, [0.0, 1.0])],
        "unit-model",
    )

    assert stored == 2
    assert store.upsert_many([], "unit-model") == 0
    assert store.count() == 2


def test_get_missing_returns_none(database_engine):
    assert _make_store(database_engine).get("chk_missing") is None


# --- Similarity ranking ------------------------------------------------------


def test_search_ranks_by_similarity(repository, database_engine):
    saved = _save(repository, id="mem_rank", _text="Ranking note.")
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    chunk_ids = ChunkRepository(sessions).replace_memory_chunks(
        saved.id,
        chunk_text(
            "The first recorded fact covers vector database indexing methods. "
            "The second recorded fact covers hybrid search ranking strategies. "
            "The third recorded fact covers local embedding model selection.",
            saved.id,
            chunk_size=100,
            overlap=10,
        ),
    )
    assert len(chunk_ids) == 3
    store = _make_store(database_engine)
    store.upsert_many(
        [
            (chunk_ids[0], saved.id, [1.0, 0.0]),
            (chunk_ids[1], saved.id, [0.0, 1.0]),
            (chunk_ids[2], saved.id, [0.7, 0.7]),
        ],
        "unit-model",
    )

    hits = store.search([1.0, 0.0], "unit-model", top_k=3)

    assert [h.chunk_id for h in hits] == [chunk_ids[0], chunk_ids[2], chunk_ids[1]]
    assert hits[0].score == pytest.approx(1.0)
    assert all(h.memory_id == saved.id for h in hits)
    # No raw vectors leak through the hit type.
    assert not any(hasattr(h, "vector") for h in hits)


def test_search_respects_top_k_and_threshold(repository, database_engine):
    saved = _save(repository, id="mem_topk", _text="Top-k note.")
    (chunk_id,) = _indexed(repository, database_engine, saved.id, "note text")
    store = _make_store(database_engine)
    store.upsert(chunk_id, saved.id, [1.0, 0.0], "unit-model")

    assert store.search([1.0, 0.0], "unit-model", top_k=0) == []
    assert store.search([1.0, 0.0], "unit-model", min_similarity=1.1) == []
    assert len(store.search([1.0, 0.0], "unit-model", top_k=5)) == 1


def test_ties_break_deterministically_by_chunk_id(repository, database_engine):
    saved = _save(repository, id="mem_tie", _text="Tie note.")
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    chunk_ids = ChunkRepository(sessions).replace_memory_chunks(
        saved.id,
        chunk_text(
            "Alpha observation about local retrieval pipelines in detail. "
            "Beta observation about semantic ranking quality in detail. "
            "Gamma observation about keyword fallback behavior in detail.",
            saved.id,
            chunk_size=100,
            overlap=10,
        ),
    )
    assert len(chunk_ids) == 3
    store = _make_store(database_engine)
    store.upsert_many(
        [(cid, saved.id, [0.5, 0.5]) for cid in chunk_ids], "unit-model"
    )

    first = [h.chunk_id for h in store.search([1.0, 1.0], "unit-model", top_k=3)]
    second = [h.chunk_id for h in store.search([1.0, 1.0], "unit-model", top_k=3)]

    assert first == second == sorted(chunk_ids)


def test_search_empty_query_rejected(database_engine):
    with pytest.raises(StorageError):
        _make_store(database_engine).search([], "unit-model")


# --- Stale vectors and model changes ------------------------------------------


def test_stale_vectors_excluded_and_reported(repository, database_engine):
    saved = _save(repository, id="mem_stale", _text="Stale vector note.")
    (chunk_id,) = _indexed(repository, database_engine, saved.id, "note text")
    store = _make_store(database_engine)
    store.upsert(chunk_id, saved.id, [1.0, 0.0, 0.0], "old-model")

    # A model change invalidates the old vector: excluded from search...
    assert store.search([1.0, 0.0, 0.0], "new-model") == []
    assert store.search([1.0, 0.0], "new-model") == []
    # ...but reported for explicit reindexing.
    assert store.stale_chunk_ids("new-model", 3) == [chunk_id]
    assert store.stale_chunk_ids("new-model", 2) == [chunk_id]
    assert store.stale_chunk_ids("old-model", 3) == []
    assert store.count("old-model") == 1
    assert store.count("new-model") == 0

    # Reindexing under the new model heals the row.
    store.upsert(chunk_id, saved.id, [1.0, 0.0], "new-model")
    assert store.stale_chunk_ids("new-model", 2) == []
    assert len(store.search([1.0, 0.0], "new-model")) == 1


# --- Deletion -----------------------------------------------------------------


def test_delete_by_chunk(repository, database_engine):
    saved = _save(repository, id="mem_del", _text="Delete vector note.")
    (chunk_id,) = _indexed(repository, database_engine, saved.id, "note text")
    store = _make_store(database_engine)
    store.upsert(chunk_id, saved.id, [1.0, 0.0], "unit-model")

    assert store.delete_by_chunk(chunk_id) is True
    assert store.delete_by_chunk(chunk_id) is False
    assert store.get(chunk_id) is None


def test_memory_deletion_cascades_to_vectors(repository, database_engine):
    saved = _save(repository, id="mem_cas", _text="Cascade note.")
    chunk_ids = _indexed(repository, database_engine, saved.id, "note text")
    store = _make_store(database_engine)
    store.upsert_many([(cid, saved.id, [1.0, 0.0]) for cid in chunk_ids], "m")
    assert store.count() == len(chunk_ids)

    assert repository.delete_by_id(saved.id) is True

    assert store.count() == 0
    # Defensive purge path stays safe to rerun after cascade deletion.
    assert store.delete_by_memory(saved.id) == 0

    assert _make_store(database_engine).get("chk_missing") is None
