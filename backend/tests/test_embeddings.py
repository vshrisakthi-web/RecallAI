"""Task 6.2 — local embedding service tests.

Every test injects a fake ``post`` transport, so the suite never starts a
model, never contacts a server, and never needs credentials. Assertions pin
the outbound request to the loopback ``/api/embed`` endpoint, prove no key or
cloud host appears anywhere, and cover batch handling, model failures,
invalid vectors, dimension mismatches, and query/document compatibility.
"""

from __future__ import annotations

import httpx
import pytest

from app.core.config import OllamaConfigError, Settings
from app.services.embeddings import (
    EmbeddingInputError,
    EmbeddingModelUnavailableError,
    EmbeddingResponseError,
    EmbeddingService,
)

VEC_A = [0.1, 0.2, 0.7]
VEC_B = [0.9, -0.3, 0.0]


def make_config(**overrides) -> Settings:
    return Settings(
        ollama_base_url=overrides.pop(
            "ollama_base_url", "http://127.0.0.1:11434"
        ),
        embedding_model=overrides.pop("embedding_model", "unit-embed-model"),
        **overrides,
    )


def make_transport(payload, status_code=200):
    calls: list = []

    def fake_post(url: str, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(
            status_code, json=payload, request=httpx.Request("POST", url)
        )

    return fake_post, calls


# --- Happy paths -------------------------------------------------------------


def test_embed_text_returns_validated_vector():
    fake_post, calls = make_transport({"embeddings": [VEC_A]})
    service = EmbeddingService(config=make_config(), post=fake_post)

    assert service.embed_text("Vector databases store embeddings.") == VEC_A
    assert len(calls) == 1


def test_embed_batch_returns_one_vector_per_input():
    fake_post, _ = make_transport({"embeddings": [VEC_A, VEC_B]})
    service = EmbeddingService(config=make_config(), post=fake_post)

    assert service.embed_batch(["first chunk", "second chunk"]) == [VEC_A, VEC_B]


def test_query_uses_same_model_and_endpoint_as_documents():
    fake_post, calls = make_transport({"embeddings": [VEC_A]})
    service = EmbeddingService(config=make_config(), post=fake_post)

    vector = service.embed_query("What did I learn about RAG?")
    url, kwargs = calls[0]

    assert vector == VEC_A
    assert url == "http://127.0.0.1:11434/api/embed"
    assert kwargs["json"] == {
        "model": "unit-embed-model",
        "input": ["What did I learn about RAG?"],
    }
    assert "key" not in str(kwargs).lower()
    assert service.model == "unit-embed-model"


def test_non_loopback_base_url_rejected_before_transport():
    fake_post, calls = make_transport({"embeddings": [VEC_A]})
    service = EmbeddingService(
        config=make_config(ollama_base_url="https://embeddings.example.com"),
        post=fake_post,
    )
    with pytest.raises(OllamaConfigError):
        service.embed_text("Private chunk text.")
    assert calls == []


# --- Input validation --------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "   ", None, 42, ["ok", ""], []])
def test_invalid_inputs_rejected(bad):
    fake_post, calls = make_transport({"embeddings": [VEC_A]})
    service = EmbeddingService(config=make_config(), post=fake_post)
    with pytest.raises(EmbeddingInputError):
        service.embed_batch(bad)  # type: ignore[arg-type]
    assert calls == []


def test_oversized_input_rejected_before_request():
    fake_post, calls = make_transport({"embeddings": [VEC_A]})
    service = EmbeddingService(
        config=make_config(max_embedding_input_chars=10), post=fake_post
    )
    with pytest.raises(EmbeddingInputError):
        service.embed_text("x" * 11)
    assert calls == []


def test_empty_question_rejected():
    fake_post, calls = make_transport({"embeddings": [VEC_A]})
    service = EmbeddingService(config=make_config(), post=fake_post)
    with pytest.raises(EmbeddingInputError):
        service.embed_query("   ")
    assert calls == []


# --- Provider failures -------------------------------------------------------


def test_connect_error_maps_to_unavailable():
    def failing_post(url: str, **kwargs):
        raise httpx.ConnectError("refused", request=httpx.Request("POST", url))

    service = EmbeddingService(config=make_config(), post=failing_post)
    with pytest.raises(EmbeddingModelUnavailableError):
        service.embed_text("chunk")


def test_404_maps_to_unavailable_model():
    fake_post, _ = make_transport({"error": "model not found"}, status_code=404)
    service = EmbeddingService(config=make_config(), post=fake_post)
    with pytest.raises(EmbeddingModelUnavailableError):
        service.embed_text("chunk")


def test_error_payload_rejected():
    fake_post, _ = make_transport({"error": "bad request"}, status_code=200)
    service = EmbeddingService(config=make_config(), post=fake_post)
    with pytest.raises(EmbeddingResponseError):
        service.embed_text("chunk")


# --- Invalid vectors ---------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"embeddings": []},  # wrong count
        {"embeddings": [[]]},  # empty vector
        {"embeddings": [[0.1, float("nan")]]},  # non-finite
        {"embeddings": [[0.1, float("inf")]]},  # non-finite
        {"embeddings": [[0.1, "x"]]},  # non-numeric
        {"embeddings": [[0.1, True]]},  # bool is not a float
        {"embeddings": [VEC_A, [0.1]]},  # mismatched dimensions
        {"no_embeddings": True},  # missing key
    ],
)
def test_invalid_vectors_rejected(payload):
    fake_post, _ = make_transport(payload)
    service = EmbeddingService(config=make_config(), post=fake_post)
    with pytest.raises(EmbeddingResponseError):
        service.embed_text("chunk")
