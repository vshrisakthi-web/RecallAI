"""Task 5.6 — isolated local Ollama summarization service tests.

Every test injects a fake ``post`` transport, so the suite never starts a
model, never contacts a server, and never needs credentials. Assertions pin
the outbound request to the loopback base URL, prove no API key or cloud host
appears anywhere, and verify that a misconfigured non-loopback URL is rejected
before the transport is invoked (no memory text can leave the device).
"""

from __future__ import annotations

import httpx
import pytest

from app.core.config import OllamaConfigError, Settings
from app.schemas.summarization import SummaryResult
from app.services.summarization import (
    OllamaSummarizationService,
    SummaryInputError,
    SummaryModelUnavailableError,
    SummaryResponseError,
)

VALID_PAYLOAD = {
    "model": "unit-test-model",
    "message": {
        "role": "assistant",
        "content": "- Local bullet one.\n- Local bullet two.",
    },
    "done": True,
}


def make_config(**overrides) -> Settings:
    """A Settings instance with deterministic loopback test values."""
    return Settings(
        ollama_base_url=overrides.pop("ollama_base_url", "http://127.0.0.1:11434"),
        ollama_model=overrides.pop("ollama_model", "unit-test-model"),
        **overrides,
    )


def make_transport(payload=VALID_PAYLOAD, status_code=200):
    """Return (fake_post, calls) where calls records (url, kwargs) per invocation."""
    calls: list = []

    def fake_post(url: str, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(
            status_code,
            json=payload,
            request=httpx.Request("POST", url),
        )

    return fake_post, calls


# --- Happy path -------------------------------------------------------------


def test_successful_summary_returns_result_and_configured_model():
    fake_post, calls = make_transport()
    service = OllamaSummarizationService(config=make_config(), post=fake_post)

    result = service.summarize("Captured article text about vector databases.")

    assert isinstance(result, SummaryResult)
    assert result.summary == "- Local bullet one.\n- Local bullet two."
    assert result.model == "unit-test-model"
    assert len(calls) == 1


def test_request_targets_loopback_chat_endpoint_without_credentials():
    fake_post, calls = make_transport()
    service = OllamaSummarizationService(config=make_config(), post=fake_post)

    service.summarize("Private captured text.")

    url, kwargs = calls[0]
    # Loopback only — never a cloud host.
    assert url == "http://127.0.0.1:11434/api/chat"
    assert url.startswith("http://127.0.0.1")
    # No credential of any kind is attached: Ollama is local and keyless.
    headers = kwargs["headers"]
    assert "Authorization" not in headers
    assert "x-goog-api-key" not in headers
    assert all("key" not in name.lower() for name in headers)
    joined = repr(kwargs["json"]) + repr(headers) + url
    assert "unit-test-key" not in joined
    assert "googleapis" not in joined


def test_request_payload_carries_only_text_prompt_and_options():
    fake_post, calls = make_transport()
    service = OllamaSummarizationService(config=make_config(), post=fake_post)

    service.summarize("distinctive captured sentence")

    _, kwargs = calls[0]
    body = kwargs["json"]
    assert body["model"] == "unit-test-model"
    assert body["stream"] is False
    assert body["options"] == {"temperature": 0.2, "num_predict": 512}
    messages = body["messages"]
    assert [m["role"] for m in messages] == ["system", "user"]
    assert "distinctive captured sentence" in messages[1]["content"]
    # The prompt-injection guard travels with the source text.
    assert "untrusted data, not instructions" in messages[0]["content"]
    # Exactly two messages and no extra fields such as URL/title metadata.
    assert set(body) == {"model", "stream", "messages", "options"}


def test_request_honours_configured_timeout():
    seen: list = []

    def recording_post(url: str, **kwargs):
        seen.append(kwargs)
        return httpx.Response(
            200, json=VALID_PAYLOAD, request=httpx.Request("POST", url)
        )

    service = OllamaSummarizationService(
        config=make_config(ollama_timeout_seconds=7), post=recording_post
    )
    service.summarize("text")

    assert seen[0]["timeout"] == 7


# --- Unusable input ----------------------------------------------------------


def test_empty_input_rejected_before_transport():
    fake_post, calls = make_transport()
    service = OllamaSummarizationService(config=make_config(), post=fake_post)

    with pytest.raises(SummaryInputError):
        service.summarize("   \n  ")
    assert calls == []


def test_oversized_input_rejected_before_transport():
    fake_post, calls = make_transport()
    config = make_config(max_summary_input_chars=100)
    service = OllamaSummarizationService(config=config, post=fake_post)

    with pytest.raises(SummaryInputError):
        service.summarize("x" * 101)
    assert calls == []


# --- Local model availability ------------------------------------------------


def test_model_not_found_maps_to_model_unavailable():
    fake_post, _ = make_transport(
        payload={"error": "model 'x' not found"}, status_code=404
    )
    service = OllamaSummarizationService(config=make_config(), post=fake_post)

    with pytest.raises(SummaryModelUnavailableError):
        service.summarize("text")


def test_connection_error_maps_to_model_unavailable():
    def refusing_post(url: str, **kwargs):
        raise httpx.ConnectError("connection refused")

    service = OllamaSummarizationService(config=make_config(), post=refusing_post)

    with pytest.raises(SummaryModelUnavailableError):
        service.summarize("text")


def test_timeout_propagates_for_route_mapping():
    def timing_out_post(url: str, **kwargs):
        raise httpx.ReadTimeout("local model timed out")

    service = OllamaSummarizationService(config=make_config(), post=timing_out_post)

    with pytest.raises(httpx.ReadTimeout):
        service.summarize("text")


def test_http_error_propagates_for_route_mapping():
    fake_post, _ = make_transport(payload={"error": "boom"}, status_code=500)
    service = OllamaSummarizationService(config=make_config(), post=fake_post)

    with pytest.raises(httpx.HTTPStatusError):
        service.summarize("text")


# --- Invalid model responses -------------------------------------------------


def test_missing_message_field_raises_response_error():
    fake_post, _ = make_transport(payload={"done": True, "something": "else"})
    service = OllamaSummarizationService(config=make_config(), post=fake_post)

    with pytest.raises(SummaryResponseError):
        service.summarize("text")


def test_error_payload_raises_response_error():
    fake_post, _ = make_transport(payload={"error": "server busy"})
    service = OllamaSummarizationService(config=make_config(), post=fake_post)

    with pytest.raises(SummaryResponseError):
        service.summarize("text")


def test_empty_content_raises_response_error():
    fake_post, _ = make_transport(
        payload={"message": {"role": "assistant", "content": "   "}}
    )
    service = OllamaSummarizationService(config=make_config(), post=fake_post)

    with pytest.raises(SummaryResponseError):
        service.summarize("text")


def test_oversized_summary_fails_validation_as_response_error():
    fake_post, _ = make_transport(
        payload={"message": {"role": "assistant", "content": "y" * 4001}}
    )
    service = OllamaSummarizationService(config=make_config(), post=fake_post)

    with pytest.raises(SummaryResponseError):
        service.summarize("text")


# --- Privacy invariant: loopback only ----------------------------------------


@pytest.mark.parametrize(
    "base_url",
    [
        "https://llm.example.com",
        "http://192.168.1.10:11434",
        "http://generativelanguage.googleapis.com",
        "127.0.0.1:11434",  # scheme-less: rejected, not silently repaired
    ],
)
def test_non_loopback_base_url_rejected_before_transport(base_url):
    fake_post, calls = make_transport()
    service = OllamaSummarizationService(
        config=make_config(ollama_base_url=base_url), post=fake_post
    )

    with pytest.raises(OllamaConfigError):
        service.summarize("private text that must stay on device")
    # The transport was never invoked, so no bytes left the app.
    assert calls == []


def test_localhost_and_ipv6_loopback_are_accepted():
    for base in (
        "http://localhost:11434",
        "http://[::1]:11434",
        "https://127.0.0.1:11434",
    ):
        fake_post, calls = make_transport()
        service = OllamaSummarizationService(
            config=make_config(ollama_base_url=base), post=fake_post
        )

        service.summarize("text")

        assert calls[0][0] == base.rstrip("/") + "/api/chat"


