"""Health and general API error tests (Module 3, Tasks 3.3, 3.9)."""

from fastapi.testclient import TestClient


def test_health_ok(client: TestClient):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": "0.4.0"}
    assert "x-request-id" in {k.lower() for k in r.headers}


def test_success_response_has_request_id_header(client: TestClient):
    from tests._factories import browser_payload

    r = client.post("/api/v1/ingest/browser", json=browser_payload())
    assert r.status_code == 201
    rid = r.headers.get("x-request-id")
    assert rid
    assert r.json()["record"]["request_id"] == rid


def test_client_provided_request_id_is_echoed(client: TestClient):
    from tests._factories import browser_payload

    r = client.post(
        "/api/v1/ingest/browser",
        json=browser_payload(),
        headers={"X-Request-ID": "trace-abc-123"},
    )
    assert r.status_code == 201
    assert r.headers.get("x-request-id") == "trace-abc-123"
    assert r.json()["record"]["request_id"] == "trace-abc-123"


def test_unsafe_request_id_rejected(client: TestClient):
    from tests._factories import browser_payload

    r = client.post(
        "/api/v1/ingest/browser",
        json=browser_payload(),
        headers={"X-Request-ID": "bad id with spaces!"},
    )
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "INVALID_REQUEST_ID"
    assert body["error"]["request_id"]


def test_malformed_json_returns_structured_error(client: TestClient):
    r = client.post(
        "/api/v1/ingest/browser",
        content=b"{ this is not valid json ",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["request_id"]
    # No stack traces / internals leaked.
    assert "Traceback" not in r.text


def test_missing_required_fields_structured_error(client: TestClient):
    r = client.post("/api/v1/ingest/browser", json={})
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert isinstance(body["error"]["details"], list)
    assert len(body["error"]["details"]) > 0
    # Details mention at least one missing field.
    joined = " ".join(d["field"] for d in body["error"]["details"])
    assert "title" in joined or "url" in joined


def test_unknown_endpoint_404(client: TestClient):
    r = client.get("/api/v1/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"
    assert r.headers["X-Request-ID"] == r.json()["error"]["request_id"]
