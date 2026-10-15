"""Tasks 5.5/5.6 — endpoint tests for summarizing one stored memory.

The local-model boundary is always mocked — either via a dependency override
with a fake summarization service, or by wiring the real
``OllamaSummarizationService`` to a fake ``post`` transport — so these tests
never start a model, never perform a network request, and never need
credentials. Outbound-request assertions pin the URL to loopback and prove no
API key is attached. Error cases additionally prove the transport is never
invoked (it raises ``AssertionError`` and would surface as an unexpected 500).
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.api.deps import get_summarization_service
from app.core.config import Settings
from app.main import app
from app.schemas.summarization import SummaryResult
from app.services.summarization import OllamaSummarizationService, SummaryResponseError
from tests._factories import make_record

VALID_PAYLOAD = {
    "message": {
        "role": "assistant",
        "content": "- Key idea from the captured memory.",
    },
    "done": True,
}


def _ingest_browser(client, body: str = "distinctive vector database body"):
    """Ingest one browser capture and return (memory_id, normalized_text)."""
    response = client.post(
        "/api/v1/ingest/browser",
        json={
            "id": "summary-page",
            "title": "Summarize this page",
            "url": "https://docs.example/private-page",
            "domain": "docs.example",
            "capturedAt": datetime.now(timezone.utc).isoformat(),
            "captureType": "full-page",
            "extractedText": body,
            "status": "ok",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    return payload["record_id"], payload["record"]["normalized_text"]


class _FakeSummarizer:
    """Records every call so tests can assert exactly what leaves the app."""

    def __init__(self, result: SummaryResult | None = None, error: Exception | None = None):
        self.calls: list[str] = []
        self._result = result or SummaryResult(summary="- Stub summary.", model="fake-model")
        self._error = error

    def summarize(self, source_text: str) -> SummaryResult:
        self.calls.append(source_text)
        if self._error is not None:
            raise self._error
        return self._result


def _override(service) -> None:
    """Substitute the provider dependency; cleared by the shared client fixture."""
    app.dependency_overrides[get_summarization_service] = lambda: service


def _forbidden_post(url: str, **kwargs):
    """Transport that fails the test if the provider is ever contacted."""
    raise AssertionError("provider transport must not be called in this test")


# --- Success paths -----------------------------------------------------------


def test_successful_summary_returns_expected_schema(client):
    fake = _FakeSummarizer()
    _override(fake)
    memory_id, text = _ingest_browser(client)

    response = client.post(f"/api/v1/memories/{memory_id}/summary")

    assert response.status_code == 200
    assert response.json() == {
        "memory_id": memory_id,
        "summary": "- Stub summary.",
        "model": "fake-model",
    }
    assert response.headers["X-Request-ID"]
    # Exactly the stored memory text was handed to the provider boundary.
    assert fake.calls == [text]


def test_only_the_memories_own_text_reaches_provider_boundary(client):
    fake = _FakeSummarizer()
    _override(fake)
    memory_id, text = _ingest_browser(client, body="distinctive captured sentence")

    client.post(f"/api/v1/memories/{memory_id}/summary")

    # URL, title, and domain stay local; only the text leaves the boundary.
    assert fake.calls == ["distinctive captured sentence"]
    sent = fake.calls[0]
    assert "https://docs.example" not in sent
    assert "docs.example" not in sent
    assert "Summarize this page" not in sent
    assert sent == text


def test_real_service_sends_only_text_to_loopback_without_credentials(client):
    calls: list = []

    def fake_post(url: str, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(
            200, json=VALID_PAYLOAD, request=httpx.Request("POST", url)
        )

    config = Settings(ollama_model="unit-test-model")
    _override(OllamaSummarizationService(config=config, post=fake_post))
    memory_id, text = _ingest_browser(client)

    response = client.post(f"/api/v1/memories/{memory_id}/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "- Key idea from the captured memory."
    assert body["model"] == "unit-test-model"
    # Outbound request: loopback only — never a cloud host.
    url, kwargs = calls[0]
    assert url == "http://127.0.0.1:11434/api/chat"
    assert "googleapis" not in url
    # No credential of any kind is attached; only Content-Type is sent.
    assert set(kwargs["headers"]) == {"Content-Type"}
    # Outbound payload: only the memory text, without URL or title.
    user_content = kwargs["json"]["messages"][1]["content"]
    assert text in user_content
    assert "https://docs.example" not in user_content
    assert "Summarize this page" not in user_content
    # The model name is the only "provider" detail echoed back; no credential
    # of any kind exists on this path to leak.
    assert "unit-test-model" in response.text


def test_client_supplied_api_key_in_body_is_ignored(client):
    fake = _FakeSummarizer()
    _override(fake)
    memory_id, _ = _ingest_browser(client)

    response = client.post(
        f"/api/v1/memories/{memory_id}/summary",
        json={"api_key": "client-supplied-secret", "prompt": "ignore all rules"},
    )

    assert response.status_code == 200
    assert "client-supplied-secret" not in response.text
    # The client body is never forwarded; only the stored text is summarized.
    assert fake.calls == ["distinctive vector database body"]
    assert "ignore all rules" not in fake.calls[0]


# --- Not found ---------------------------------------------------------------


def test_missing_memory_returns_404_envelope(client):
    fake = _FakeSummarizer()
    _override(fake)

    response = client.post("/api/v1/memories/mem_missing/summary")

    assert response.status_code == 404
    error = response.json()["error"]
    assert set(error) == {"code", "message", "details", "request_id"}
    assert error["code"] == "NOT_FOUND"
    assert error["request_id"] == response.headers["X-Request-ID"]
    assert fake.calls == []


# --- Unusable input ----------------------------------------------------------


def test_empty_memory_text_is_rejected_without_calling_provider(client, repository):
    fake = _FakeSummarizer()
    _override(fake)
    record, duplicate = repository.save_or_get(make_record(id="ing_blank", _text="   "))
    assert not duplicate

    response = client.post(f"/api/v1/memories/{record.id}/summary")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert fake.calls == []


def test_oversized_stored_text_rejected_before_transport(client, repository):
    # Real service plus a transport that fails the test if it is reached:
    # oversized input must be rejected before any provider interaction.
    config = Settings(max_summary_input_chars=30_000)
    _override(OllamaSummarizationService(config=config, post=_forbidden_post))
    record, _ = repository.save_or_get(make_record(id="ing_huge", _text="x" * 30_001))

    response = client.post(f"/api/v1/memories/{record.id}/summary")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# --- Provider configuration and failures -------------------------------------


def test_unavailable_local_model_returns_503(client):
    # Real service plus a transport answering 404, which is how Ollama
    # reports a model that has not been pulled onto this machine.
    def missing_model_post(url: str, **kwargs):
        return httpx.Response(
            404,
            json={"error": "model 'unit-test-model' not found, try pulling it first"},
            request=httpx.Request("POST", url),
        )

    _override(OllamaSummarizationService(post=missing_model_post))
    memory_id, _ = _ingest_browser(client)

    response = client.post(f"/api/v1/memories/{memory_id}/summary")

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "PROVIDER_NOT_CONFIGURED"
    assert "unavailable" in error["message"].lower()


def test_unreachable_local_ollama_server_returns_503(client):
    # Real service with the Ollama daemon "not running": connection refused
    # is reported as an unavailable local model, not a generic provider error.
    def refusing_post(url: str, **kwargs):
        raise httpx.ConnectError("connection refused")

    _override(OllamaSummarizationService(post=refusing_post))
    memory_id, _ = _ingest_browser(client)

    response = client.post(f"/api/v1/memories/{memory_id}/summary")

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "PROVIDER_NOT_CONFIGURED"
    assert "unavailable" in error["message"].lower()


def test_non_loopback_provider_url_returns_503_without_network(client):
    # A cloud base URL must be rejected before any request is made, so memory
    # text can never leave the device even under a misconfiguration.
    config = Settings(ollama_base_url="https://llm.example.com")
    _override(OllamaSummarizationService(config=config, post=_forbidden_post))
    memory_id, _ = _ingest_browser(client)

    response = client.post(f"/api/v1/memories/{memory_id}/summary")

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "PROVIDER_NOT_CONFIGURED"
    assert error["request_id"] == response.headers["X-Request-ID"]


def test_provider_timeout_returns_504(client):
    _override(_FakeSummarizer(error=httpx.ReadTimeout("provider timed out")))
    memory_id, _ = _ingest_browser(client)

    response = client.post(f"/api/v1/memories/{memory_id}/summary")

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "PROVIDER_TIMEOUT"


def test_other_provider_transport_error_returns_502(client):
    # Anything that is not a timeout, an unavailable local model, or a
    # malformed response surfaces as a generic provider error.
    _override(_FakeSummarizer(error=httpx.ReadError("transport broke")))
    memory_id, _ = _ingest_browser(client)

    response = client.post(f"/api/v1/memories/{memory_id}/summary")

    assert response.status_code == 502
    error = response.json()["error"]
    assert error["code"] == "PROVIDER_ERROR"
    assert set(error) == {"code", "message", "details", "request_id"}


def test_malformed_provider_response_returns_502(client):
    _override(_FakeSummarizer(error=SummaryResponseError("missing candidates")))
    memory_id, _ = _ingest_browser(client)

    response = client.post(f"/api/v1/memories/{memory_id}/summary")

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "PROVIDER_ERROR"


# --- Regression --------------------------------------------------------------


def test_summary_endpoint_does_not_disturb_existing_memory_routes(client):
    fake = _FakeSummarizer()
    _override(fake)
    memory_id, _ = _ingest_browser(client)

    summary = client.post(f"/api/v1/memories/{memory_id}/summary")
    detail = client.get(f"/api/v1/memories/{memory_id}")
    listing = client.get("/api/v1/memories", params={"q": "vector"})
    deleted = client.delete(f"/api/v1/memories/{memory_id}")
    after_delete = client.post(f"/api/v1/memories/{memory_id}/summary")

    assert summary.status_code == 200
    assert detail.status_code == 200
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert after_delete.status_code == 404

