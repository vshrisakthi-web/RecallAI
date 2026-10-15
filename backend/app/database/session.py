"""SQLite engine and session management for the local structured-memory store."""

from __future__ import annotations

import os
from typing import Iterator, Optional

from sqlalchemy import URL, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.database.models import Base


def database_url(path: Optional[str] = None) -> URL:
    """Build a SQLite URL from a file path without string-escaping path chars."""
    return URL.create("sqlite", database=path or settings.database_path)


def create_database_engine(path: Optional[str] = None) -> Engine:
    """Create a SQLite engine; tests can pass a disposable database path."""
    database_path = path or settings.database_path
    if database_path != ":memory:":
        database_path = os.path.abspath(database_path)
        os.makedirs(os.path.dirname(database_path), exist_ok=True)

    engine = create_engine(
        database_url(database_path),
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker] = None


def get_engine() -> Engine:
    """Return the lazily created engine for the configured development DB."""
    global _engine
    if _engine is None:
        _engine = create_database_engine()
    return _engine


def get_session_local() -> sessionmaker:
    """Return a session factory bound to the configured development DB."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _session_factory


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a session and closes it after the request."""
    db = get_session_local()()
    try:
        yield db
    finally:
        db.close()


def init_db(engine: Optional[Engine] = None) -> None:
    """Create mapped tables for isolated tests; production uses Alembic migrations."""
    Base.metadata.create_all(bind=engine or get_engine())