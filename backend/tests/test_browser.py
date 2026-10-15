"""Browser capture ingestion tests (Module 3, Task 3.10)."""

from fastapi.testclient import TestClient

from tests._factories import browser_payload


def test_valid_browser_record_accepted(client: TestClient):
    r = client.post("/api/v1/ingest/browser", json=browser_payload())
    assert r.status_code == 201
    body = r.json()
    assert body["duplicate"] is False
    assert body["status"] == "created"
    assert body["record_id"]
    rec = body["record"]
    # Fields preserved from the extension record.
    assert rec["title"] == "Understanding Vector Databases"
    assert rec["source_url"] == "https://techblog.example/vector-db"
    assert rec["domain"] == "techblog.example"
    assert rec["source_type"] == "browser"
    assert rec["capture_type"] == "full-page"
    assert rec["normalized_text"].startswith("Vector databases store embeddings")
    assert rec["content_hash"]
    assert rec["captured_at"].endswith("+00:00") or rec["captured_at"].endswith("Z")


def test_selected_text_capture(client: TestClient):
    payload = browser_payload(
        captureType="selection",
        extractedText="chosen phrase",
        selectedText="chosen phrase",
        surroundingContext="The paragraph containing the chosen phrase.",
    )
    r = client.post("/api/v1/ingest/browser", json=payload)
    assert r.status_code == 201
    rec = r.json()["record"]
    assert rec["capture_type"] == "selection"
    assert rec["selected_text"] == "chosen phrase"
    assert rec["surrounding_context"].startswith("The paragraph")


def test_selection_without_selected_text_rejected(client: TestClient):
    payload = browser_payload(captureType="selection", selectedText=None)
    r = client.post("/api/v1/ingest/browser", json=payload)
    assert r.status_code == 422


def test_invalid_url_rejected(client: TestClient):
    r = client.post("/api/v1/ingest/browser", json=browser_payload(url="not a url", domain="not a url"))
    assert r.status_code == 422


def test_unsupported_scheme_rejected(client: TestClient):
    r = client.post(
        "/api/v1/ingest/browser",
        json=browser_payload(url="javascript:alert(1)", domain=""),
    )
    assert r.status_code == 422


def test_invalid_domain_metadata_rejected(client: TestClient):
    r = client.post(
        "/api/v1/ingest/browser",
        json=browser_payload(domain="evil.other.com"),
    )
    assert r.status_code == 422
    assert "does not match" in r.text


def test_invalid_timestamp_rejected(client: TestClient):
    r = client.post("/api/v1/ingest/browser", json=browser_payload(capturedAt="not-a-timestamp"))
    assert r.status_code == 422


def test_timezone_naive_timestamp_rejected(client: TestClient):
    r = client.post("/api/v1/ingest/browser", json=browser_payload(capturedAt="2026-01-02T03:04:05"))
    assert r.status_code == 422
    assert "timezone" in r.text.lower()


def test_oversized_content_rejected(client: TestClient):
    r = client.post("/api/v1/ingest/browser", json=browser_payload(extractedText="x" * 200_001))
    assert r.status_code == 422


def test_empty_content_rejected(client: TestClient):
    r = client.post("/api/v1/ingest/browser", json=browser_payload(extractedText="   \n  "))
    assert r.status_code == 422


def test_repeated_identical_capture_is_duplicate(client: TestClient):
    r1 = client.post("/api/v1/ingest/browser", json=browser_payload())
    assert r1.status_code == 201
    r2 = client.post("/api/v1/ingest/browser", json=browser_payload())
    assert r2.status_code == 200
    assert r2.json()["duplicate"] is True
    assert r2.json()["status"] == "duplicate"
    assert r2.json()["record_id"] == r1.json()["record_id"]


def test_changed_content_same_url_creates_new_record(client: TestClient):
    r1 = client.post("/api/v1/ingest/browser", json=browser_payload(extractedText="version one"))
    r2 = client.post("/api/v1/ingest/browser", json=browser_payload(extractedText="version two"))
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r2.json()["duplicate"] is False
    assert r2.json()["record_id"] != r1.json()["record_id"]
