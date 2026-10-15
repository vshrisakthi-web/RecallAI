"""Pytest configuration and shared fixtures (Module 3, Task 3.10).

Each test gets an isolated JSON storage file (in a temp dir) via a dependency
override, so tests never touch real user data or each other's state.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_repository
from app.main import app
from app.database.session import create_database_engine
from app.repositories.sqlite_store import MemoryRepository


@pytest.fixture
def storage_path(tmp_path) -> str:
    """An isolated JSON file retained for legacy repository/import tests."""
    return str(tmp_path / "ingested.json")


@pytest.fixture
def database_path(tmp_path) -> str:
    return str(tmp_path / "recallai.db")


@pytest.fixture
def database_engine(database_path):
    """A separately migrated database for every test that needs SQLite."""
    engine = create_database_engine(database_path)
    config = Config("alembic.ini")
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def repository(database_engine):
    return MemoryRepository(sessionmaker(bind=database_engine, expire_on_commit=False))


@pytest.fixture
def client(repository) -> TestClient:
    """A TestClient backed by an isolated migrated SQLite database."""

    def _override_repo():
        return repository

    app.dependency_overrides[get_repository] = _override_repo
    yield TestClient(app)
    app.dependency_overrides.clear()
