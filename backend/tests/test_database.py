import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.database.session import create_database_engine
from app.repositories.base import StorageError
from app.repositories.sqlite_store import MemoryRepository
from tests._factories import make_record


def test_fresh_database_has_expected_schema_and_foreign_keys(database_engine):
    with database_engine.connect() as connection:
        tables = set(
            connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).scalars()
        )
        assert {"sources", "memories", "conversations", "tasks", "alembic_version"} <= tables
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert connection.execute(
            text("SELECT name FROM sqlite_master WHERE name='memories_fts'")
        ).scalar() == "memories_fts"


def test_migration_is_repeatable_and_preserves_database_records(database_path, database_engine):
    repository = MemoryRepository(sessionmaker(bind=database_engine, expire_on_commit=False))
    stored, _ = repository.save_or_get(make_record(id="before-upgrade", _text="keep me"))

    config = Config("alembic.ini")
    with database_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

    restarted_engine = create_database_engine(database_path)
    try:
        restarted = MemoryRepository(sessionmaker(bind=restarted_engine, expire_on_commit=False))
        assert restarted.get_by_id(stored.id).normalized_text == "keep me"
    finally:
        restarted_engine.dispose()


def test_transaction_rolls_back_source_when_memory_write_fails(repository, database_engine):
    record = make_record(
        id="bad-metadata",
        source_type="browser",
        source_url="https://rollback.example/",
        domain="rollback.example",
        source_metadata={"not-json": object()},
    )
    with pytest.raises(StorageError):
        repository.save_or_get(record)

    with database_engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM sources")).scalar() == 0
        assert connection.execute(text("SELECT count(*) FROM memories")).scalar() == 0


def test_database_failure_is_wrapped_as_storage_error(tmp_path):
    corrupt_path = tmp_path / "corrupt.db"
    corrupt_path.write_text("not a SQLite database", encoding="utf-8")
    engine = create_database_engine(str(corrupt_path))
    try:
        repository = MemoryRepository(sessionmaker(bind=engine))
        with pytest.raises(StorageError):
            repository.count()
    finally:
        engine.dispose()
