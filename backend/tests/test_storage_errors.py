"""Storage-failure and no-partial-record tests (Module 3, Task 3.10)."""

from fastapi.testclient import TestClient

from app.api.deps import get_repository
from app.main import app
from app.repositories.base import IngestionRepository, StorageError
from sqlalchemy.orm import sessionmaker

from app.database.session import create_database_engine
from app.repositories.sqlite_store import MemoryRepository
from app.schemas.common import CanonicalRecord
from tests._factories import browser_payload


class FailingRepository(IngestionRepository):
    def save_or_get(self, record: CanonicalRecord):
        raise StorageError("simulated disk failure")

    def get_by_id(self, record_id: str):
        return None

    def list_recent(self, limit: int = 50):
        return []

    def count(self) -> int:
        return 0


def test_storage_error_returns_structured_500_without_traceback():
    app.dependency_overrides[get_repository] = lambda: FailingRepository()
    try:
        with TestClient(app) as client:
            r = client.post("/api/v1/ingest/browser", json=browser_payload())
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 500
    body = r.json()
    assert body["error"]["code"] == "STORAGE_ERROR"
    assert body["error"]["request_id"]
    # No stack traces, file paths, or internals leaked to the client.
    text = r.text
    assert "Traceback" not in text
    assert "simulated disk failure" not in text
    assert ".py" not in text


def test_failed_validation_leaves_no_partial_record(client: TestClient, repository):
    # An invalid request must not persist anything.
    bad = client.post("/api/v1/ingest/browser", json={"title": "only a title"})
    assert bad.status_code == 422

    # A subsequent valid request is a genuine create (proving nothing leaked).
    good = client.post("/api/v1/ingest/browser", json=browser_payload())
    assert good.status_code == 201
    assert good.json()["duplicate"] is False

    assert repository.count() == 1


def test_record_actually_persisted_to_disk(client: TestClient, database_path):
    r = client.post("/api/v1/ingest/browser", json=browser_payload(id="persist_me"))
    assert r.status_code == 201
    record_id = r.json()["record_id"]

    # A new engine and repository simulate stopping and restarting the backend.
    engine = create_database_engine(database_path)
    try:
        repo = MemoryRepository(sessionmaker(bind=engine, expire_on_commit=False))
        stored = repo.get_by_id(record_id)
        assert stored is not None
        assert stored.title == "Understanding Vector Databases"
    finally:
        engine.dispose()
