"""Transcript import tests (Module 3, Task 3.7, 3.10)."""

from fastapi.testclient import TestClient

from tests._factories import transcript_payload


def test_valid_transcript_accepted(client: TestClient):
    r = client.post("/api/v1/ingest/transcript", json=transcript_payload())
    assert r.status_code == 201
    body = r.json()
    assert body["duplicate"] is False
    rec = body["record"]
    assert rec["source_type"] == "transcript"
    assert rec["source_url"] == "https://podcast.example/ep12"
    assert rec["domain"] == "podcast.example"
    assert rec["source_metadata"]["source"] == "podcast.example"
    assert rec["source_metadata"]["duration_seconds"] == 1820
    assert "running language models locally" in rec["normalized_text"]


def test_missing_transcript_text_rejected(client: TestClient):
    r = client.post("/api/v1/ingest/transcript", json={"title": "no text"})
    assert r.status_code == 422


def test_oversized_transcript_rejected(client: TestClient):
    r = client.post("/api/v1/ingest/transcript", json=transcript_payload(transcript="x" * 500_001))
    assert r.status_code == 422


def test_identical_transcript_deduplicated(client: TestClient):
    r1 = client.post("/api/v1/ingest/transcript", json=transcript_payload())
    r2 = client.post("/api/v1/ingest/transcript", json=transcript_payload())
    assert r1.status_code == 201
    assert r2.status_code == 200
    assert r2.json()["duplicate"] is True
    assert r2.json()["record_id"] == r1.json()["record_id"]


def test_optional_url_validated(client: TestClient):
    r = client.post("/api/v1/ingest/transcript", json=transcript_payload(source_url="ftp://bad"))
    assert r.status_code == 422


def test_transcript_without_url_accepted(client: TestClient):
    payload = transcript_payload()
    payload.pop("source_url", None)
    payload.pop("source", None)
    r = client.post("/api/v1/ingest/transcript", json=payload)
    assert r.status_code == 201
    assert r.json()["record"]["source_url"] is None


def test_invalid_metadata_rejected(client: TestClient):
    r = client.post(
        "/api/v1/ingest/transcript",
        json=transcript_payload(metadata={"blob": "x" * 1001}),
    )
    assert r.status_code == 422
