"""Application configuration (Module 3).

Explicit, documented limits and settings. Values can be overridden via
environment variables prefixed with ``RECALLAI_`` (see ``.env.example``).
No secrets are stored here; the API is intended for local development only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlsplit


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _positive_int_env(name: str, default: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer between 1 and {maximum}.") from exc
    if value < 1 or value > maximum:
        raise ValueError(f"{name} must be an integer between 1 and {maximum}.")
    return value


def _non_empty_env(name: str, default: str) -> str:
    value = os.environ.get(name, default).strip()
    if not value:
        raise ValueError(f"{name} must not be empty.")
    return value


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number.") from exc


def _gemini_api_key_from_env() -> Optional[str]:
    return os.environ.get("RECALLAI_GEMINI_API_KEY", "").strip() or None


class GeminiConfigError(RuntimeError):
    """The hosted summarization provider has no API key configured.

    Subclasses ``RuntimeError`` so existing callers that catch ``RuntimeError``
    (Module 5, Task 5.2 tests) keep working, while the API layer (Task 5.5) can
    distinguish "not configured" from other runtime failures.
    """


class OllamaConfigError(RuntimeError):
    """The local Ollama summarization endpoint is misconfigured.

    Raised when ``RECALLAI_OLLAMA_BASE_URL`` does not resolve to a loopback
    host, which would let memory text leave the device. Subclasses
    ``RuntimeError`` for the same reason as :class:`GeminiConfigError`, so the
    API layer can map it onto its 503 "provider not configured" response.
    """


class VoiceConfigError(RuntimeError):
    """The isolated speech-to-text worker is not installed or not usable.

    Raised when ``.venv-voice`` or the worker script is missing. Subclasses
    ``RuntimeError`` so the API layer maps it onto HTTP 503, matching how
    :class:`OllamaConfigError` is treated.
    """


# Only loopback targets are accepted for summarization (Module 5, Task 5.6):
# memory text must never leave the machine, so no cloud host can ever be set.
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


@dataclass(frozen=True)
class Settings:
    """Tunable limits and behaviour for the ingestion pipeline."""

    # --- Text size limits (characters) -------------------------------------
    # Chosen to comfortably fit a long article while preventing unbounded
    # payloads. All limits are enforced at the Pydantic boundary.
    max_browser_text: int = _int_env("RECALLAI_MAX_BROWSER_TEXT", 200_000)
    max_transcript_text: int = _int_env("RECALLAI_MAX_TRANSCRIPT_TEXT", 500_000)
    max_note_text: int = _int_env("RECALLAI_MAX_NOTE_TEXT", 50_000)
    max_selection_text: int = _int_env("RECALLAI_MAX_SELECTION_TEXT", 50_000)
    max_context_text: int = _int_env("RECALLAI_MAX_CONTEXT_TEXT", 50_000)
    max_title: int = _int_env("RECALLAI_MAX_TITLE", 300)
    max_url: int = _int_env("RECALLAI_MAX_URL", 2048)
    # Number of key/value pairs allowed in a source-metadata object.
    max_metadata_items: int = _int_env("RECALLAI_MAX_METADATA_ITEMS", 50)
    max_metadata_value: int = _int_env("RECALLAI_MAX_METADATA_VALUE", 1000)
    max_metadata_depth: int = _int_env("RECALLAI_MAX_METADATA_DEPTH", 2)

    # --- Request ID --------------------------------------------------------
    max_request_id: int = _int_env("RECALLAI_MAX_REQUEST_ID", 128)

    # --- Timestamp sanity range -------------------------------------------
    # Reject timestamps more than this far in the future (clock skew guard) and
    # anything unreasonably far in the past. Justification: ingestion records
    # represent "now or past" events; wild future dates indicate a bad client.
    max_future_skew_minutes: int = _int_env("RECALLAI_MAX_FUTURE_SKEW_MINUTES", 60 * 24)
    min_year: int = _int_env("RECALLAI_MIN_YEAR", 2000)

    # --- Storage -----------------------------------------------------------
    # JSON-file-backed repository. Path is overridable; tests use a temp dir.
    # Default: <backend>/data/ingested.json (git-ignored; never committed).
    storage_path: str = os.environ.get(
        "RECALLAI_STORAGE_PATH",
        os.path.join(
            os.path.dirname(__file__),  # .../backend/app/core
            "..",
            "..",
            "data",
            "ingested.json",
        ),
    )

    # SQLite file; RECALLAI_DB_PATH can point tests or users at a separate file.
    database_path: str = os.environ.get(
        "RECALLAI_DB_PATH",
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "data",
            "recallai.db",
        ),
    )

    # --- CORS --------------------------------------------------------------
    # Permit only the two standard local Vite development origins by default.
    cors_allow_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.environ.get(
            "RECALLAI_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    )

    # --- Hosted summarization (Module 5) ----------------------------------
    # Credentials are optional so ingestion and memory browsing work without
    # provider configuration. The secret is deliberately excluded from repr.
    gemini_api_key: Optional[str] = field(default_factory=_gemini_api_key_from_env, repr=False)
    gemini_model: str = field(
        default_factory=lambda: _non_empty_env(
            "RECALLAI_GEMINI_MODEL", "gemini-3.8-flash"
        )
    )
    gemini_timeout_seconds: int = field(
        default_factory=lambda: _positive_int_env(
            "RECALLAI_GEMINI_TIMEOUT_SECONDS", 30, 120
        )
    )
    max_summary_input_chars: int = field(
        default_factory=lambda: _positive_int_env(
            "RECALLAI_MAX_SUMMARY_INPUT_CHARS", 30_000, 200_000
        )
    )

    # --- Local Ollama inference (Module 5 summarization, Module 6 RAG) ------
    # The summary and ask endpoints talk to a local Ollama server over loopback
    # only. No credential exists for this path because nothing leaves the
    # device. RAG reuses the same audited setting so the privacy invariant
    # stays in one place.
    ollama_base_url: str = field(
        default_factory=lambda: _non_empty_env(
            "RECALLAI_OLLAMA_BASE_URL", "http://127.0.0.1:11434"
        )
    )
    ollama_model: str = field(
        default_factory=lambda: _non_empty_env(
            "RECALLAI_OLLAMA_MODEL", "llama3.2"
        )
    )
    ollama_timeout_seconds: int = field(
        default_factory=lambda: _positive_int_env(
            "RECALLAI_OLLAMA_TIMEOUT_SECONDS", 30, 120
        )
    )

    # --- RAG retrieval (Module 6) -------------------------------------------
    # Chunking (Task 6.1). 1200 chars fits the local embedding model with
    # headroom; 150 chars of overlap repeats ~1-2 sentences across boundaries.
    rag_chunk_size: int = field(
        default_factory=lambda: _positive_int_env(
            "RECALLAI_RAG_CHUNK_SIZE", 1200, 8000
        )
    )
    rag_chunk_overlap: int = field(
        default_factory=lambda: _int_env("RECALLAI_RAG_CHUNK_OVERLAP", 150)
    )

    # Embeddings (Task 6.2). Loopback-only, like summarization: chunk text and
    # questions must never leave the device, so require_ollama_base_url() is
    # re-used before any request.
    embedding_model: str = field(
        default_factory=lambda: _non_empty_env(
            "RECALLAI_EMBEDDING_MODEL", "nomic-embed-text"
        )
    )
    embedding_timeout_seconds: int = field(
        default_factory=lambda: _positive_int_env(
            "RECALLAI_EMBEDDING_TIMEOUT_SECONDS", 60, 300
        )
    )
    # Bounded before embedding so one oversized chunk cannot balloon memory
    # usage; the server would truncate beyond its own context window anyway.
    max_embedding_input_chars: int = field(
        default_factory=lambda: _positive_int_env(
            "RECALLAI_MAX_EMBEDDING_INPUT_CHARS", 6000, 20000
        )
    )

    # Retrieval (Tasks 6.4-6.6). Each channel contributes up to
    # candidates_per_channel ranked candidates; fusion keeps top_k evidence
    # chunks. The similarity floor applies to the semantic channel only
    # (BM25/LIKE keyword scores are not comparable to cosine).
    rag_candidates_per_channel: int = field(
        default_factory=lambda: _positive_int_env(
            "RECALLAI_RAG_CANDIDATES", 20, 100
        )
    )
    rag_top_k: int = field(
        default_factory=lambda: _positive_int_env("RECALLAI_RAG_TOP_K", 6, 20)
    )
    rag_min_similarity: float = field(
        default_factory=lambda: _float_env(
            "RECALLAI_RAG_MIN_SIMILARITY", 0.25
        )
    )
    # Reciprocal-rank-fusion weights (Task 6.5); equal by default so neither
    # channel dominates and ties are broken deterministically by chunk id.
    rag_semantic_weight: float = field(
        default_factory=lambda: _float_env(
            "RECALLAI_RAG_SEMANTIC_WEIGHT", 1.0
        )
    )
    rag_keyword_weight: float = field(
        default_factory=lambda: _float_env("RECALLAI_RAG_KEYWORD_WEIGHT", 1.0)
    )
    rrf_k: int = field(
        default_factory=lambda: _positive_int_env("RECALLAI_RAG_RRF_K", 60, 1000)
    )

    # Prompt and answer budget (Tasks 6.7, 6.9). ~6000 chars of evidence plus
    # instructions fits a 4k-token local context window with margin.
    rag_evidence_budget_chars: int = field(
        default_factory=lambda: _positive_int_env(
            "RECALLAI_RAG_EVIDENCE_BUDGET_CHARS", 6000, 30000
        )
    )
    rag_max_question_chars: int = field(
        default_factory=lambda: _positive_int_env(
            "RECALLAI_RAG_MAX_QUESTION_CHARS", 1000, 4000
        )
    )

    # Confidence thresholds (Task 6.9). Cosine similarities, so they must sit in
    # [-1, 1]. A best match below ``confidence_weak`` is reported as weak rather
    # than presented as a confident answer; at or above ``confidence_strong``
    # (with enough passages) it is reported as strong. Kept as configuration so
    # the behaviour is tunable and testable rather than a hard-coded guess.
    rag_confidence_weak: float = field(
        default_factory=lambda: _float_env("RECALLAI_RAG_CONFIDENCE_WEAK", 0.35)
    )
    rag_confidence_strong: float = field(
        default_factory=lambda: _float_env("RECALLAI_RAG_CONFIDENCE_STRONG", 0.55)
    )
    # Independent passages needed before evidence may be called strong.
    rag_min_evidence_for_strong: int = field(
        default_factory=lambda: _positive_int_env(
            "RECALLAI_RAG_MIN_EVIDENCE_FOR_STRONG", 2, 10
        )
    )

    # --- Agent harness (Module 8, Task 71) ----------------------------------
    # Bounded inputs, outputs, and execution for the workflow pipeline. Every
    # limit is explicit so one runaway stage cannot balloon context, memory, or
    # runtime. RECALLAI_AGENT_* overrides follow the same env rules as the
    # settings above. Defaults are documented in backend/.env.example and in
    # docs/module-8-agent-harness.md.
    #
    # Kept equal to AskRequest.question (POST /api/v1/ask, max 1000 chars) so
    # the workflow accepts exactly the questions the Ask API accepts.
    agent_max_query_chars: int = field(
        default_factory=lambda: _positive_int_env(
            "RECALLAI_AGENT_MAX_QUERY_CHARS", 1000, 4000
        )
    )
    # Evidence items and total evidence characters handed to the analysis
    # stage. The character budget mirrors rag_evidence_budget_chars by default
    # but is independently tunable, so workflow context stays inside the local
    # model window even if the Ask budget is changed later.
    agent_max_evidence_items: int = field(
        default_factory=lambda: _positive_int_env(
            "RECALLAI_AGENT_MAX_EVIDENCE_ITEMS", 8, 50
        )
    )
    agent_max_evidence_chars: int = field(
        default_factory=lambda: _positive_int_env(
            "RECALLAI_AGENT_MAX_EVIDENCE_CHARS", 6000, 30000
        )
    )
    # Proposed task draft bounds. Drafts are workflow state only and are never
    # written to the tasks table before an explicit user approval (Task 79).
    agent_max_tasks: int = field(
        default_factory=lambda: _positive_int_env("RECALLAI_AGENT_MAX_TASKS", 5, 20)
    )
    agent_max_task_title_chars: int = field(
        default_factory=lambda: _positive_int_env(
            "RECALLAI_AGENT_MAX_TASK_TITLE_CHARS", 200, 500
        )
    )
    agent_max_task_description_chars: int = field(
        default_factory=lambda: _positive_int_env(
            "RECALLAI_AGENT_MAX_TASK_DESCRIPTION_CHARS", 1000, 5000
        )
    )
    # Execution bounds: one stage call, then the whole run, then bounded
    # attempts (an initial try plus at most one repair of a recoverable format
    # error). Validation, permission, and malformed-request errors are never
    # retried.
    agent_stage_timeout_seconds: int = field(
        default_factory=lambda: _positive_int_env(
            "RECALLAI_AGENT_STAGE_TIMEOUT_SECONDS", 30, 120
        )
    )
    agent_total_budget_seconds: int = field(
        default_factory=lambda: _positive_int_env(
            "RECALLAI_AGENT_TOTAL_BUDGET_SECONDS", 120, 600
        )
    )
    agent_max_attempts: int = field(
        default_factory=lambda: _positive_int_env("RECALLAI_AGENT_MAX_ATTEMPTS", 2, 5)
    )
    # Cap on user-facing errors retained on one run (oldest dropped first, so
    # the newest failure is always visible). Stage traces stay bounded by the
    # number of stages times max attempts.
    agent_max_errors: int = field(
        default_factory=lambda: _positive_int_env("RECALLAI_AGENT_MAX_ERRORS", 10, 100)
    )

    # --- Voice input (Module 9, Task 82) ------------------------------------
    # STT runs in an *isolated* venv (.venv-voice, Python 3.12) behind a
    # subprocess boundary, so faster-whisper and its native wheels never enter
    # the .venv-mcp test environment. The interpreter and worker script paths
    # default to the in-repo locations and are overridable for CI or a custom
    # install; require_voice_worker() is the single availability gate.
    voice_python: str = os.environ.get(
        "RECALLAI_VOICE_PYTHON",
        os.path.join(
            os.path.dirname(__file__),  # .../backend/app/core
            "..",
            "..",
            ".venv-voice",
            "bin",
            "python",
        ),
    )
    voice_worker: str = os.environ.get(
        "RECALLAI_VOICE_WORKER",
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "voice",
            "transcribe_worker.py",
        ),
    )
    # Hugging Face snapshot name or local dir; "tiny/base/small" resolve from
    # the cache on first use (see docs/module-9-voice.md for sizes).
    voice_model: str = field(
        default_factory=lambda: _non_empty_env("RECALLAI_VOICE_MODEL", "base")
    )
    voice_timeout_seconds: int = field(
        default_factory=lambda: _positive_int_env("RECALLAI_VOICE_TIMEOUT_SECONDS", 120, 600)
    )
    # Upload ceiling (bytes) and decoded-audio ceiling (seconds). The byte cap
    # is enforced in the API before any temp file; the duration cap is enforced
    # inside the worker *after* decode but *before* model inference, so a
    # long file costs decoding time only, never inference time.
    max_voice_audio_bytes: int = field(
        default_factory=lambda: _positive_int_env(
            "RECALLAI_MAX_VOICE_AUDIO_BYTES", 10 * 1024 * 1024, 100 * 1024 * 1024
        )
    )
    max_voice_audio_seconds: int = field(
        default_factory=lambda: _positive_int_env(
            "RECALLAI_MAX_VOICE_AUDIO_SECONDS", 120, 600
        )
    )

    def require_gemini_api_key(self) -> str:
        """Return the configured secret only when a hosted request is requested."""
        if not self.gemini_api_key:
            raise GeminiConfigError(
                "Hosted summarization is not configured. Set "
                "RECALLAI_GEMINI_API_KEY in the backend environment."
            )
        return self.gemini_api_key

    def require_ollama_base_url(self) -> str:
        """Return the Ollama base URL after enforcing a loopback target.

        Privacy invariant: summarization traffic may only target this machine,
        so a non-loopback or scheme-less URL raises :class:`OllamaConfigError`
        (mapped to HTTP 503) before any request — and therefore any memory
        text — can leave the device.
        """
        base = self.ollama_base_url.rstrip("/")
        parts = urlsplit(base)
        if parts.scheme not in {"http", "https"} or parts.hostname not in _LOOPBACK_HOSTS:
            raise OllamaConfigError(
                "Local summarization must target a loopback Ollama server: "
                "RECALLAI_OLLAMA_BASE_URL must be an http(s) URL on localhost, "
                "127.0.0.1, or ::1."
            )
        return base

    def require_voice_worker(self) -> tuple[str, str]:
        """Return ``(voice_python, voice_worker)`` after checking they exist.

        The STT stack lives in a separate venv on purpose (see the voice
        settings block), so "not installed" is a normal, recoverable state —
        the API maps this onto HTTP 503 with setup instructions, exactly like
        an unconfigured Ollama endpoint.
        """
        python = os.path.abspath(self.voice_python)
        worker = os.path.abspath(self.voice_worker)
        if not os.path.isfile(python) or not os.path.isfile(worker):
            raise VoiceConfigError(
                "Speech transcription is not installed. Create the voice "
                "environment as described in docs/module-9-voice.md."
            )
        return python, worker


settings = Settings()
