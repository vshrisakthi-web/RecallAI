from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.database.models import Source
from app.database.session import create_database_engine, init_db
from app.repositories.sqlite_store import MemoryRepository
from tests._factories import make_record


def _record(identifier, body, **overrides):
    return make_record(id=identifier, _text=body, **overrides)


def test_create_read_source_and_delete_keeps_source(repository):
    stored, duplicate = repository.save_or_get(
        _record(
            "browser-1",
            "A searchable browser capture",
            source_type="browser",
            source_url="https://docs.example/page",
            domain="docs.example",
            source_metadata={"capture": "full-page"},
        )
    )

    assert not duplicate
    assert repository.get_by_id(stored.id).normalized_text == "A searchable browser capture"
    memory = repository.get_by_id(stored.id)
    assert memory is not None
    assert memory.source_url == "https://docs.example/page"
    assert memory.source_id is not None
    source = repository.get_source(memory.source_id)
    assert source is not None
    assert source["memory_count"] == 1
    assert repository.delete_by_id(stored.id)
    source = repository.get_source(memory.source_id)
    assert source is not None
    assert source["memory_count"] == 0


def test_identical_retries_are_idempotent_but_changed_page_is_kept(repository):
    first, duplicate = repository.save_or_get(
        _record("one", "same body", source_type="browser", source_url="https://x.example/a", domain="x.example")
    )
    retry, duplicate_retry = repository.save_or_get(
        _record("two", "same body", source_type="browser", source_url="https://x.example/a", domain="x.example")
    )
    changed, duplicate_changed = repository.save_or_get(
        _record("three", "changed body", source_type="browser", source_url="https://x.example/a", domain="x.example")
    )

    assert not duplicate and duplicate_retry and not duplicate_changed
    assert retry.id == first.id
    assert changed.id == "three"
    assert repository.count() == 2


def test_manual_notes_without_urls_are_supported_and_not_merged_by_title(repository):
    first, duplicate_a = repository.save_or_get(_record("note-1", "first note", title="Same title"))
    second, duplicate_b = repository.save_or_get(_record("note-2", "second note", title="Same title"))

    assert not duplicate_a and not duplicate_b
    assert first.source_url is None and second.source_url is None
    assert repository.count() == 2


def test_search_filters_combination_and_stable_pagination(repository):
    same_url = "https://docs.example/guide"
    repository.save_or_get(
        _record(
            "b1", "searchable first article", source_type="browser", source_url=same_url,
            domain="docs.example", captured_at=datetime(2026, 10, 10, 2, tzinfo=timezone.utc),
        )
    )
    repository.save_or_get(
        _record(
            "b2", "searchable second article", source_type="browser", source_url=same_url,
            domain="docs.example", captured_at=datetime(2026, 10, 10, 5, tzinfo=timezone.utc),
        )
    )
    repository.save_or_get(
        _record(
            "t1", "searchable podcast", source_type="transcript",
            source_url="https://audio.example/episode", domain="audio.example",
            captured_at=datetime(2026, 10, 10, 4, tzinfo=timezone.utc),
        )
    )
    repository.save_or_get(
        _record(
            "n1", "searchable private note", source_type="note",
            captured_at=datetime(2026, 10, 9, 4, tzinfo=timezone.utc),
        )
    )

    first_page, total = repository.list_memories(
        query="searchable",
        from_date=date(2026, 10, 10),
        to_date=date(2026, 10, 10),
        domain="docs.example",
        source_type="browser",
        page=1,
        page_size=1,
    )
    second_page, _ = repository.list_memories(
        query="searchable", domain="docs.example", source_type="browser", page=2, page_size=1
    )

    assert total == 2
    assert [memory.id for memory in first_page] == ["b2"]
    assert [memory.id for memory in second_page] == ["b1"]


def test_delete_removes_memory_from_search_and_missing_delete_is_false(repository):
    record, _ = repository.save_or_get(_record("delete-me", "unique needle"))
    assert repository.list_memories(query="needle")[1] == 1
    assert repository.delete_by_id(record.id)
    assert repository.list_memories(query="needle")[1] == 0
    assert not repository.delete_by_id(record.id)


def test_foreign_key_prevents_deleting_a_source_in_use(repository, database_engine):
    stored, _ = repository.save_or_get(
        _record("kept", "source must remain", source_type="browser", source_url="https://x.example/", domain="x.example")
    )
    memory = repository.get_by_id(stored.id)
    sessions = sessionmaker(bind=database_engine)
    with pytest.raises(IntegrityError):
        with sessions.begin() as session:
            source = session.scalar(select(Source).where(Source.canonical_source_url == memory.source_url))
            session.delete(source)


def test_like_fallback_works_when_database_has_no_fts5(tmp_path):
    engine = create_database_engine(str(tmp_path / "no-fts.db"))
    try:
        init_db(engine)
        repository = MemoryRepository(sessionmaker(bind=engine, expire_on_commit=False))
        repository.save_or_get(_record("fallback", "fallback searchable word"))
        records, total = repository.list_memories(query="searchable")
        assert total == 1
        assert records[0].id == "fallback"
    finally:
        engine.dispose()
