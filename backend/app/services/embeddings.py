"""Local embedding service for retrieval (Module 6, Task 6.2).

Converts memory chunks and user questions into vectors using a local
embedding model served by Ollama — the same loopback-only path that Module 5
summarization uses. Chunk text and questions must never leave the device, so
the base URL goes through ``Settings.require_ollama_base_url()`` before
every request, exactly like the summarizer.

Embedding model: ``nomic-embed-text`` (137M params, ~274 MB download, 768
dimensions, 2048-token context). Chosen over the generation model
(``llama3.2:1b``, which has no embedding head) because a dedicated
contrastively-trained embedding model ranks semantic similarity far better at
one-fifth the download size. Model id and dimensions are stored with every
vector (Task 6.3) so a later model change is detected instead of silently
comparing incompatible vectors.

Transport is injected (``post`` callable), mirroring the Module 5 summarizer
seam — tests use a fake transport, never a live model. Single, batch, and
query embedding share one code path so documents and queries always use the
same model. Ollama's ``/api/embed`` takes ``{"model", "input"}`` where input
is one string or a list, and answers ``{"embeddings": [[float...], ...]}``.
Vectors are validated (finite, non-empty, consistent dims) because a NaN or
truncated vector would silently corrupt ranking.
"""

from __future__ import annotations

import math
from typing import Callable, Optional, Sequence

import httpx

from app.core.config import Settings, settings


class EmbeddingInputError(ValueError):
    """Raised when text is empty or exceeds the configured input limit."""


class EmbeddingModelUnavailableError(RuntimeError):
    """Raised when the local Ollama server or embedding model is unavailable.

    The daemon is not reachable, or Ollama answered 404 because the model has
    not been pulled. The API layer maps this onto HTTP 503.
    """


class EmbeddingResponseError(RuntimeError):
    """Raised on malformed vectors or dimension mismatch in the response."""


class EmbeddingService:
    """Embed chunk text and questions with a local Ollama embedding model.

    The contract mirrors ``OllamaSummarizationService`` (Module 5, Task 5.6):
    loopback-only, credential-free, injectable transport.
    """

    def __init__(
        self,
        config: Settings = settings,
        post: Optional[Callable[..., httpx.Response]] = None,
    ) -> None:
        self._config = config
        self._post = post or httpx.post

    @property
    def model(self) -> str:
        return self._config.embedding_model

    def embed_text(self, text: str) -> list[float]:
        """Embed one chunk or document; returns a validated vector."""
        (vector,) = self.embed_batch([text])
        return vector

    def embed_query(self, question: str) -> list[float]:
        """Embed a user question with the same model as documents.

        Compatibility matters: retrieval compares this vector against stored
        chunk vectors, so the query path must never use a different model.
        """
        if not isinstance(question, str) or not question.strip():
            raise EmbeddingInputError("The question must not be empty.")
        return self.embed_text(question)

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of chunk texts; returns one vector per input."""
        inputs = self._validate_inputs(texts)

        # Enforced before any request: a non-loopback URL raises instead of
        # letting memory text travel off-device.
        base_url = self._config.require_ollama_base_url()
        model = self._config.embedding_model
        try:
            response = self._post(
                f"{base_url}/api/embed",
                headers={"Content-Type": "application/json"},
                json={"model": model, "input": inputs},
                timeout=self._config.embedding_timeout_seconds,
            )
        except httpx.ConnectError as exc:
            raise EmbeddingModelUnavailableError(
                "The local Ollama server is not reachable."
            ) from exc

        # Ollama answers 404 when the configured model has not been pulled.
        if response.status_code == 404:
            raise EmbeddingModelUnavailableError(
                f"The local embedding model '{model}' is not available."
            )
        response.raise_for_status()

        try:
            payload = response.json()
        except ValueError as exc:
            raise EmbeddingResponseError(
                "Ollama returned a malformed embedding response."
            ) from exc
        if isinstance(payload, dict) and isinstance(payload.get("error"), str):
            raise EmbeddingResponseError("Ollama rejected the embedding request.")
        try:
            raw_vectors = payload["embeddings"]
        except (KeyError, TypeError) as exc:
            raise EmbeddingResponseError(
                "Ollama returned an embedding response without vectors."
            ) from exc
        return self._validate_vectors(raw_vectors, expected_count=len(inputs))

    def _validate_inputs(self, texts: Sequence[str]) -> list[str]:
        if not isinstance(texts, Sequence) or isinstance(texts, (str, bytes)):
            raise EmbeddingInputError("Provide a list of texts to embed.")
        inputs = list(texts)
        if not inputs:
            raise EmbeddingInputError("Provide at least one text to embed.")
        limit = self._config.max_embedding_input_chars
        cleaned: list[str] = []
        for text in inputs:
            if not isinstance(text, str) or not text.strip():
                raise EmbeddingInputError(
                    "Every text to embed must be a non-empty string."
                )
            if len(text) > limit:
                raise EmbeddingInputError(
                    "A text exceeds the configured embedding input limit."
                )
            cleaned.append(text)
        return cleaned

    @staticmethod
    def _validate_vectors(raw: object, expected_count: int) -> list[list[float]]:
        if not isinstance(raw, list) or len(raw) != expected_count:
            raise EmbeddingResponseError(
                "Ollama returned an unexpected number of embedding vectors."
            )
        vectors: list[list[float]] = []
        dimensions: int | None = None
        for entry in raw:
            if not isinstance(entry, list) or not entry:
                raise EmbeddingResponseError(
                    "Ollama returned an empty embedding vector."
                )
            vector: list[float] = []
            for value in entry:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise EmbeddingResponseError(
                        "Ollama returned a non-numeric embedding value."
                    )
                number = float(value)
                if not math.isfinite(number):
                    raise EmbeddingResponseError(
                        "Ollama returned a non-finite embedding value."
                    )
                vector.append(number)
            if dimensions is None:
                dimensions = len(vector)
            elif len(vector) != dimensions:
                raise EmbeddingResponseError(
                    "Ollama returned vectors with mismatched dimensions."
                )
            vectors.append(vector)
        return vectors
