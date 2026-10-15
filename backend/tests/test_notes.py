"""Manual notes import tests (Module 3, Task 3.8, 3.10)."""

from fastapi.testclient import TestClient

from tests._factories import note_payload


def test_valid_note_accepted(client: TestClient):
    r = client.post("/api/v1/ingest/notes", json=note_payload())
    assert r.status_code == 201
    body = r.json()
    assert body["duplicate"] is False
    rec = body["record"]
    assert rec["source_type"] == "note"
    assert rec["source_url"] is None
    assert rec["source_metadata"]["tags"] == ["reading", "vector-search"]
    assert "HNSW paper" in rec["normalized_text"]


def test_note_without_url_accepted(client: TestClient):
    r = client.post("/api/v1/ingest/notes", json=note_payload())
    assert r.status_code == 201
    assert r.json()["record"]["source_url"] is None


def test_empty_note_rejected(client: TestClient):
    r = client.post("/api/v1/ingest/notes", json=note_payload(note="   \n "))
    assert r.status_code == 422


def test_oversized_note_rejected(client: TestClient):
    r = client.post("/api/v1/ingest/notes", json=note_payload(note="x" * 50_001))
    assert r.status_code == 422


def test_duplicate_note_handled_consistently(client: TestClient):
    r1 = client.post("/api/v1/ingest/notes", json=note_payload())
    r2 = client.post("/api/v1/ingest/notes", json=note_payload())
    assert r1.status_code == 201
    assert r2.status_code == 200
    assert r2.json()["duplicate"] is True
    assert r2.json()["record_id"] == r1.json()["record_id"]


def test_distinct_notes_same_title_not_merged(client: TestClient):
    r1 = client.post("/api/v1/ingest/notes", json=note_payload(title="Ideas", note="first idea"))
    r2 = client.post("/api/v1/ingest/notes", json=note_payload(title="Ideas", note="second idea"))
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r2.json()["record_id"] != r1.json()["record_id"]


def test_invalid_metadata_rejected(client: TestClient):
    r = client.post(
        "/api/v1/ingest/notes",
        json=note_payload(metadata={"blob": "x" * 1001}),
    )
    assert r.status_code == 422


def test_note_with_reference_url(client: TestClient):
    r = client.post(
        "/api/v1/ingest/notes",
        json=note_payload(source_url="https://docs.example/hnsw"),
    )
    assert r.status_code == 201
    assert r.json()["record"]["source_url"] == "https://docs.example/hnsw"
    assert r.json()["record"]["domain"] == "docs.example"
