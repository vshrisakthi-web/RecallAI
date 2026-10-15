"""Task 6.5 — keyword retrieval over the chunk FTS index.

These tests exist because the first implementation of ``_search_fts`` could
never execute: it referenced a non-existent column and used an alias where
SQLite's FTS5 requires the real table name. Nothing imported the module, so the
defect was invisible. Every test here runs against a real migrated SQLite
database with real FTS5, so the SQL is genuinely exercised.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import sessionmaker

from app.repositories.base import StorageError
from app.repositories.chunk_store import ChunkRepository
from app.repositories.sqlite_store import MemoryRepository
from app.services.chunking import chunk_text
from app.services.keyword_search import KeywordSearchService, extract_terms
from tests._factories import make_record, utcnow

NOW = datetime(2026, 10, 12, 12, 0, 0, tzinfo=timezone.utc)


def index(repository, sessions, memory_id, text, title="A note", captured_at=None, **kwargs):
    """Save a memory and index its chunks (which also fills chunk_fts)."""
    saved, _ = repository.save_or_get(
        make_record(
            id=memory_id,
            _text=text,
            title=title,
            captured_at=captured_at or utcnow(),
            **kwargs,
        )
    )
    ChunkRepository(sessions).replace_memory_chunks(
        saved.id, chunk_text(saved.normalized_text, saved.id)
    )
    return saved


def service(database_engine):
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    return KeywordSearchService(sessions), sessions


# --- Term extraction -------------------------------------------------------


def test_extract_terms_lowercases_dedupes_and_preserves_order():
    assert extract_terms("How does HNSW index embeddings?") == [
        "hnsw",
        "index",
        "embeddings",
    ]


def test_extract_terms_honours_limit_and_drops_punctuation():
    assert extract_terms("RAG, RAG! RAG; retrieval — embeddings.", limit=2) == ["rag", "retrieval"]


def test_extract_terms_returns_empty_for_punctuation_only():
    assert extract_terms("!!! ??? ...") == []


def test_extract_terms_drops_stopwords_so_questions_can_match():
    """Without stopword removal an AND query would require filler words."""
    assert extract_terms("What did I learn about RAG last week?") == [
        "learn",
        "rag",
        "last",
        "week",
    ]


def test_extract_terms_falls_back_when_only_stopwords_present():
    # "is" is a stopword, so the meaningful list is empty and the raw tokens
    # (deduped) are used instead — the caller still searches for something.
    assert extract_terms("what is it?") == ["what", "is", "it"]


# --- FTS5 path (the previously broken code) --------------------------------


def test_fts_search_finds_an_exact_token(repository, database_engine):
    kw, sessions = service(database_engine)
    index(repository, sessions, "mem_a", "HNSW graphs and IVF lists index embeddings.")
    index(repository, sessions, "mem_b", "Pasta needs salted boiling water.")

    hits = kw.search("How does HNSW index embeddings?")

    assert [hit.memory_id for hit in hits] == ["mem_a"]
    assert hits[0].rank == 1


def test_fts_search_ranks_are_one_based_and_ordered(repository, database_engine):
    kw, sessions = service(database_engine)
    index(repository, sessions, "mem_a", "HNSW graphs index embeddings for search.")
    index(repository, sessions, "mem_b", "HNSW graphs and IVF lists also index embeddings.")

    hits = kw.search("HNSW graphs index embeddings")

    assert hits, "AND semantics should match both chunks"
    assert [hit.rank for hit in hits] == list(range(1, len(hits) + 1))


def test_fts_and_semantics_requires_every_term(repository, database_engine):
    """A chunk missing any query term must not match (precision over recall)."""
    kw, sessions = service(database_engine)
    index(repository, sessions, "mem_partial", "HNSW graphs for similarity search.")
    index(repository, sessions, "mem_full", "HNSW graphs and IVF lists index embeddings.")

    hits = kw.search("HNSW embeddings")

    assert [hit.memory_id for hit in hits] == ["mem_full"]


def test_fts_search_matches_memory_title_too(repository, database_engine):
    """The FTS row mirrors the memory title, so titles are searchable."""
    kw, sessions = service(database_engine)
    index(repository, sessions, "mem_t", "A short body of text.", title="Ollama notes")

    assert [hit.memory_id for hit in kw.search("ollama")] == ["mem_t"]


def test_fts_no_match_returns_empty_list_not_an_error(repository, database_engine):
    kw, sessions = service(database_engine)
    index(repository, sessions, "mem_a", "HNSW graphs index embeddings.")

    assert kw.search("zzzzz qqqqq") == []


def test_fts_honours_the_inclusive_date_window(repository, database_engine):
    kw, sessions = service(database_engine)
    index(
        repository, sessions, "mem_new", "HNSW graphs index embeddings.",
        captured_at=datetime(2026, 10, 10, tzinfo=timezone.utc),
    )
    index(
        repository, sessions, "mem_old", "HNSW graphs index embeddings.",
        captured_at=NOW - timedelta(days=90),
    )

    hits = kw.search("HNSW embeddings", from_date=date(2026, 10, 1), to_date=date(2026, 10, 31))
    assert [hit.memory_id for hit in hits] == ["mem_new"]


def test_fts_limit_caps_the_result_count(repository, database_engine):
    kw, sessions = service(database_engine)
    # Distinct bodies: identical text is deduplicated by content hash.
    for n in range(5):
        index(repository, sessions, f"mem_{n}", f"HNSW graphs index embeddings number {n}.")

    assert len(kw.search("HNSW embeddings", limit=2)) == 2


def test_fts_widens_from_and_to_or_when_nothing_matches_all_terms(
    repository, database_engine
):
    """No chunk holds every term, so OR widening surfaces partial matches."""
    kw, sessions = service(database_engine)
    index(repository, sessions, "mem_a", "HNSW graphs for similarity search.")
    index(repository, sessions, "mem_b", "Embeddings are dense vectors of numbers.")

    hits = kw.search("HNSW embeddings")

    assert {hit.memory_id for hit in hits} == {"mem_a", "mem_b"}
    assert [hit.rank for hit in hits] == [1, 2]


def test_fts_prefers_precise_and_match_over_widening(repository, database_engine):
    """A chunk matching every term must not be diluted by OR-only chunks."""
    kw, sessions = service(database_engine)
    index(repository, sessions, "mem_exact", "HNSW graphs index embeddings for search.")
    index(repository, sessions, "mem_partial", "Embeddings are dense vectors of numbers.")

    hits = kw.search("HNSW embeddings")

    assert [hit.memory_id for hit in hits] == ["mem_exact"]


def test_fts_deleted_memory_is_excluded(repository, database_engine):
    kw, sessions = service(database_engine)
    index(repository, sessions, "mem_a", "HNSW graphs index embeddings for search.")
    index(repository, sessions, "mem_b", "HNSW graphs also index embeddings efficiently.")
    assert {hit.memory_id for hit in kw.search("HNSW embeddings")} == {"mem_a", "mem_b"}

    assert repository.delete_by_id("mem_a") is True

    assert [hit.memory_id for hit in kw.search("HNSW embeddings")] == ["mem_b"]


# --- LIKE fallback path ----------------------------------------------------


def test_like_fallback_used_when_fts_table_is_absent(repository, database_engine):
    """Older databases without FTS5 must degrade ranking, not correctness."""
    kw, sessions = service(database_engine)
    index(repository, sessions, "mem_a", "HNSW graphs and IVF lists index embeddings.")
    index(repository, sessions, "mem_b", "Pasta needs salted boiling water.")

    with database_engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE chunk_fts")

    hits = kw.search("hnsw embeddings")
    assert [hit.memory_id for hit in hits] == ["mem_a"]
    assert hits[0].rank == 1


def test_like_fallback_excludes_deleted_memories(repository, database_engine):
    kw, sessions = service(database_engine)
    index(repository, sessions, "mem_a", "HNSW graphs index embeddings for search.")
    index(repository, sessions, "mem_b", "HNSW graphs also index embeddings efficiently.")
    # Delete BEFORE dropping the FTS table: the delete trigger fires on DELETE
    # and would fail against a missing table.
    repository.delete_by_id("mem_a")

    with database_engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE chunk_fts")

    assert [hit.memory_id for hit in kw.search("hnsw embeddings")] == ["mem_b"]


def test_like_fallback_honours_the_date_window(repository, database_engine):
    kw, sessions = service(database_engine)
    index(
        repository, sessions, "mem_new", "HNSW graphs index embeddings.",
        captured_at=datetime(2026, 10, 10, tzinfo=timezone.utc),
    )
    index(
        repository, sessions, "mem_old", "HNSW graphs index embeddings.",
        captured_at=NOW - timedelta(days=90),
    )
    with database_engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE chunk_fts")

    hits = kw.search("hnsw embeddings", from_date=date(2026, 10, 1), to_date=date(2026, 10, 31))
    assert [hit.memory_id for hit in hits] == ["mem_new"]


# --- Failure mapping -------------------------------------------------------


def test_empty_question_short_circuits_without_touching_the_database(repository, database_engine):
    """No terms means no query at all — not an error, just no results."""
    kw, sessions = service(database_engine)
    index(repository, sessions, "mem_a", "HNSW graphs index embeddings.")

    class _Unreachable:
        def __getattr__(self, _name):
            raise AssertionError("the database must not be queried for an empty question")

    kw._sessions = lambda: _Unreachable()
    assert kw.search("!!! ??? ...") == []


def test_database_failure_maps_to_storage_error(repository, database_engine):
    kw, _ = service(database_engine)

    class _Exploding:
        def scalar(self, *_a, **_k):
            raise StorageError("simulated keyword index failure")

        def close(self):
            return None

    real_factory = kw._sessions
    kw._sessions = lambda: _Exploding()
    try:
        with pytest.raises(StorageError):
            kw.search("hnsw")
    finally:
        kw._sessions = real_factory

