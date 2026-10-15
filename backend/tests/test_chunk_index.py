"""Task 6.1 — chunk persistence and indexing lifecycle tests.

Covers metadata preservation (chunk → memory/source resolution), idempotent
reindexing (no duplicates), memory updates swapping chunks, and memory
deletion purging chunks. Uses the transactional ChunkRepository against the
per-test migrated SQLite database (``repository`` fixture).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import sessionmaker

from app.repositories.chunk_store import ChunkRepository
from app.services.chunking import chunk_text
from tests._factories import make_record, utcnow


def _save(repository, **overrides):
    record = make_record(**overrides)
    saved, _ = repository.save_or_get(record)
    return saved


def _chunks(repository, sessions, memory_id: str, text: str):
    return ChunkRepository(sessions).replace_memory_chunks(
        memory_id, chunk_text(text, memory_id)
    )


def test_chunks_preserve_source_metadata_via_memory(repository, database_engine):
    saved = _save(
        repository,
        id="mem_rag",
        source_type="browser",
        title="Understanding Vector Databases",
        _text="Vector databases store embeddings and enable fast similarity search.",
        source_url="https://techblog.example/vector-db",
        domain="techblog.example",
    )
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    stored = _chunks(repository, sessions, saved.id, saved.normalized_text)

    rows = ChunkRepository(sessions).get_chunks(saved.id)
    assert [r.id for r in rows] == stored
    (row,) = rows
    assert row.chunk_text == saved.normalized_text
    assert row.start_offset == 0
    assert row.end_offset == len(saved.normalized_text)

    # The source metadata lives on the memory record, not the chunk row.
    fetched = repository.get_by_id(saved.id)
    assert fetched is not None
    assert fetched.title == "Understanding Vector Databases"
    assert fetched.source_url == "https://techblog.example/vector-db"
    assert fetched.domain == "techblog.example"


def test_reindexing_is_idempotent(repository, database_engine):
    saved = _save(
        repository,
        id="mem_loop",
        _text="Stable content reindexes to stable chunk ids.",
    )
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    repo = ChunkRepository(sessions)
    first = repo.replace_memory_chunks(
        saved.id, chunk_text(saved.normalized_text, saved.id)
    )
    second = repo.replace_memory_chunks(
        saved.id, chunk_text(saved.normalized_text, saved.id)
    )
    assert first == second
    assert repo.count_chunks(saved.id) == len(first)
    assert repo.count_chunks() == len(first)


def test_memory_update_refreshes_chunks(repository, database_engine):
    saved = _save(repository, id="mem_edit", _text="Original note text here.")
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    repo = ChunkRepository(sessions)
    before = repo.replace_memory_chunks(
        saved.id, chunk_text(saved.normalized_text, saved.id)
    )
    new_text = "Revised note text with more detail added here for retrieval."
    updated = make_record(id="mem_edit", _text=new_text)
    repository.save_or_get(updated)
    after = repo.replace_memory_chunks(saved.id, chunk_text(new_text, saved.id))
    assert before != after
    rows = repo.get_chunks(saved.id)
    assert [r.id for r in rows] == after
    assert rows[0].chunk_text.startswith("Revised note")


def test_memory_deletion_removes_chunks(repository, database_engine):
    saved = _save(repository, id="mem_gone", _text="Temporary note to delete.")
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    repo = ChunkRepository(sessions)
    repo.replace_memory_chunks(saved.id, chunk_text(saved.normalized_text, saved.id))
    assert repo.count_chunks(saved.id) == 1
    assert repository.delete_by_id(saved.id) is True
    # FK cascade removes chunk rows with the memory; the store-level delete is
    # a no-op but must stay safe to rerun.
    assert repo.count_chunks(saved.id) == 0
    assert repo.delete_memory_chunks(saved.id) == 0


def test_get_by_id_and_count_across_memories(repository, database_engine):
    first = _save(repository, id="mem_one", _text="First memory note.")
    second = _save(repository, id="mem_two", _text="Second memory note.")
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    repo = ChunkRepository(sessions)
    ids_one = _chunks(repository, sessions, first.id, first.normalized_text)
    ids_two = _chunks(repository, sessions, second.id, second.normalized_text)
    row = repo.get_by_id(ids_one[0])
    assert row is not None and row.memory_id == first.id
    assert repo.get_by_id("chk_missing") is None
    assert repo.count_chunks() == len(ids_one) + len(ids_two)


def test_chunk_offsets_index_into_normalized_text():
    text = " ".join(f"Sentence {n} about retrieval systems." for n in range(30))
    chunks = chunk_text(text, "mem_ts", chunk_size=200, overlap=40)
    assert len(chunks) >= 3
    for chunk in chunks:
        # Slicing the original text with the stored offsets reproduces the
        # chunk exactly, including transcript-like line breaks and unicode.
        assert text[chunk.start_offset:chunk.end_offset] == chunk.text


def test_transcript_like_and_unicode_chunk_round_trip():
    text = "Host: ようこそ。 Today we discuss RAG 😊.\n\nGuest: 検索拡張生成です。"
    chunks = chunk_text(text, "mem_uni")
    assert chunks
    for chunk in chunks:
        assert text[chunk.start_offset:chunk.end_offset] == chunk.text
