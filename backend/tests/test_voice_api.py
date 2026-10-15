"""Task 82 — endpoint tests for speech-to-text over the isolated worker.

Every test substitutes the subprocess boundary: the service is constructed
with a fake ``runner`` (the same seam style as ``OllamaSummarizationService(post=...)``),
so no model is downloaded, no worker process is started, and no microphone is
needed. ``voice_python``/``voice_worker`` point at touched files in a temp dir
so ``require_voice_worker()`` passes its existence gate, and ``temp_dir`` points
at ``tmp_path`` so temporary-file cleanup is directly observable.

Beyond status codes, these tests pin the safety contract: raw audio is gone
after every call (success, failure, timeout), error bodies never leak temp
paths, and the transcript never reaches the logs.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_transcription_service
from app.core.config import settings
from app.main import app
from app.services.stt import TranscriptionService
from app.api.routes import voice as voice_routes

# A minimal header-only WAV: enough for magic-byte sniffing (RIFF....WAVE).
FAKE_WAV = (
    b"RIFF"
    + (36).to_bytes(4, "little")
    + b"WAVE"
    + b"fmt "
    + (16).to_bytes(4, "little")
    + b"\x01\x00\x01\x00"
    + b"\x40\x1f\x00\x00\x80\x3e\x00\x00\x02\x00\x10\x00"
    + b"data"
    + (0).to_bytes(4, "little")
    + b"\x00\x00\x00\x00" * 8
)


def _ok_payload(**overrides) -> dict:
    payload = {
        "ok": True,
        "text": "How do HNSW graphs work?",
        "language": "en",
        "duration_seconds": 2.5,
        "model": "base",
    }
    payload.update(overrides)
    return payload


class FakeRunner:
    """Stands in for ``subprocess.run``; records argv and returns canned output."""

    def __init__(self, result=None, error: Exception | None = None):
        self.calls: list[dict] = []
        self._result = result
        self._error = error

    def __call__(self, command, **kwargs):
        self.calls.append({"command": command, **kwargs})
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return subprocess.CompletedProcess(command, *self._result)


def _completed(stdout: str, returncode: int = 0):
    """Build (result tuple) for FakeRunner: (returncode, stdout, stderr)."""
    return (returncode, stdout, "")


def _env(tmp_path, runner, **config_overrides) -> TranscriptionService:
    """Service wired to fake worker files, a fake runner, and a temp dir."""
    python = tmp_path / "fake-python"
    worker = tmp_path / "fake-worker.py"
    python.touch()
    worker.touch()
    config = dataclasses.replace(
        settings,
        voice_python=str(python),
        voice_worker=str(worker),
        **config_overrides,
    )
    return TranscriptionService(runner=runner, config=config, temp_dir=str(tmp_path))


def _override(service: TranscriptionService) -> None:
    app.dependency_overrides[get_transcription_service] = lambda: service


def _post(client: TestClient, body: bytes = FAKE_WAV, content_type: str = "audio/wav"):
    return client.post(
        "/api/v1/voice/transcribe",
        files={"file": ("clip.wav", body, content_type)},
    )


def _leftover_audio(tmp_path) -> list:
    return list(tmp_path.glob("recallai-voice-*"))


# --- Success path ------------------------------------------------------------


def test_successful_transcription_returns_schema_and_cleans_up(client, tmp_path):
    runner = FakeRunner(result=_completed(json.dumps(_ok_payload()) + "\n"))
    _override(_env(tmp_path, runner))
    response = _post(client)

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "transcript": "How do HNSW graphs work?",
        "language": "en",
        "duration_seconds": 2.5,
        "model": "base",
    }

    # The worker was invoked exactly once, with the documented argv protocol:
    # <python> <worker> <audio> <model> <max_seconds>.
    assert len(runner.calls) == 1
    command = runner.calls[0]["command"]
    assert command[0].endswith("fake-python")
    assert command[1].endswith("fake-worker.py")
    assert command[3] == "base"
    assert command[4] == str(settings.max_voice_audio_seconds)
    # The upload really reached the worker as a file on disk.
    audio_path = command[2]
    assert audio_path.startswith(str(tmp_path))

    # Raw audio is deleted immediately after the call (success path).
    assert _leftover_audio(tmp_path) == []


def test_success_tolerates_incidental_stdout_chatter(client, tmp_path):
    """Library chatter on stdout must not corrupt the one-line JSON protocol."""
    payload = json.dumps(_ok_payload(text="Chatter tolerated.")) + "\n"
    runner = FakeRunner(result=_completed("ct2: loaded int8 kernel\n" + payload))
    _override(_env(tmp_path, runner))
    response = _post(client)

    assert response.status_code == 200
    assert response.json()["transcript"] == "Chatter tolerated."


def test_content_type_codecs_parameter_is_accepted(client, tmp_path):
    """Browsers send ``audio/webm; codecs=opus`` — the codecs part is ignored."""
    runner = FakeRunner(result=_completed(json.dumps(_ok_payload()) + "\n"))
    _override(_env(tmp_path, runner))
    response = _post(client, content_type="audio/webm; codecs=opus")

    assert response.status_code == 200


def test_transcript_never_appears_in_logs(client, tmp_path, caplog):
    secret = "the passphrase is hunter two"
    runner = FakeRunner(result=_completed(json.dumps(_ok_payload(text=secret)) + "\n"))
    _override(_env(tmp_path, runner))

    # The alembic test fixture runs logging.config.fileConfig(), whose default
    # disable_existing_loggers=True silences loggers created earlier (including
    # recallai.voice). Re-enable just this logger so the assertion is real.
    logging.getLogger("recallai.voice").disabled = False

    with caplog.at_level("INFO", logger="recallai.voice"):
        response = _post(client)

    assert response.status_code == 200
    assert secret not in caplog.text
    # Byte counts and durations are logged; content is not.
    assert "transcription ok" in caplog.text


# --- Upload validation (must all reject BEFORE any worker is spawned) -------


def _forbidden_runner():
    def _run(*args, **kwargs):
        raise AssertionError("worker must not be spawned for an invalid upload")

    return _run


def test_missing_file_field_returns_422(client, tmp_path):
    _override(_env(tmp_path, FakeRunner(result=_completed(json.dumps(_ok_payload())))))
    response = client.post("/api/v1/voice/transcribe")  # no multipart file at all

    assert response.status_code == 422
    assert _leftover_audio(tmp_path) == []


def test_empty_upload_returns_422(client, tmp_path):
    _override(_env(tmp_path, _forbidden_runner()))
    response = _post(client, body=b"")

    assert response.status_code == 422
    assert "empty" in response.json()["error"]["message"].lower()


def test_unsupported_content_type_returns_422(client, tmp_path):
    _override(_env(tmp_path, _forbidden_runner()))
    response = _post(client, content_type="text/plain")

    assert response.status_code == 422
    assert "unsupported audio format" in response.json()["error"]["message"].lower()


def test_magic_byte_mismatch_returns_422(client, tmp_path):
    """A text file mislabelled as audio/wav is caught by sniffing, not the label."""
    _override(_env(tmp_path, _forbidden_runner()))
    response = _post(
        client, body=b"this is definitely not audio content at all", content_type="audio/wav"
    )

    assert response.status_code == 422
    assert "does not look like" in response.json()["error"]["message"].lower()


def test_riff_but_not_wave_is_rejected(client, tmp_path):
    """Bare RIFF is ambiguous (AVI); only RIFF....WAVE passes as wav."""
    avi = b"RIFF" + (36).to_bytes(4, "little") + b"AVI " + b"\x00" * 32
    _override(_env(tmp_path, _forbidden_runner()))
    response = _post(client, body=avi, content_type="audio/wav")

    assert response.status_code == 422


def test_oversized_upload_returns_422(client, tmp_path, monkeypatch):
    small_limit = dataclasses.replace(settings, max_voice_audio_bytes=64)
    monkeypatch.setattr(voice_routes, "settings", small_limit)
    _override(_env(tmp_path, _forbidden_runner()))
    # Valid WAV header padded far beyond the 64-byte limit.
    response = _post(client, body=FAKE_WAV + b"\x00" * 4096)

    assert response.status_code == 422
    assert "exceeds" in response.json()["error"]["message"].lower()


# --- Worker failure mapping --------------------------------------------------


def _fail_payload(kind: str, message: str) -> str:
    return json.dumps({"ok": False, "kind": kind, "message": message}) + "\n"


@pytest.mark.parametrize(
    ("kind", "expected_status", "expected_fragment"),
    [
        ("invalid-audio", 422, "safe message"),
        ("no-speech", 422, "safe message"),
        ("too-long", 422, "safe message"),
        ("model-load-failed", 503, "safe message"),
        # Unknown kinds (incl. "worker-error") are 502 with the route's FIXED
        # message — worker-supplied text deliberately stays server-side.
        ("worker-error", 502, "failed unexpectedly"),
    ],
)
def test_classified_worker_failures_map_to_expected_status(
    client, tmp_path, kind, expected_status, expected_fragment
):
    runner = FakeRunner(result=_completed(_fail_payload(kind, "safe message"), returncode=2))
    _override(_env(tmp_path, runner))
    response = _post(client)

    assert response.status_code == expected_status
    assert expected_fragment in response.json()["error"]["message"]
    # Worker ran (this is post-validation), but its failure is reported, not swallowed.
    assert len(runner.calls) == 1
    # Audio handed to the worker is cleaned up even on failure.
    assert _leftover_audio(tmp_path) == []


def test_timeout_returns_504_and_kills_and_cleans_up(client, tmp_path):
    timeout = subprocess.TimeoutExpired(cmd=["fake-python"], timeout=120)
    runner = FakeRunner(error=timeout)
    _override(_env(tmp_path, runner))
    response = _post(client)

    assert response.status_code == 504
    assert "too long" in response.json()["error"]["message"].lower()
    # subprocess.run(timeout=) kills the child before raising; nothing left to clean.
    assert _leftover_audio(tmp_path) == []


def test_malformed_worker_stdout_returns_502(client, tmp_path):
    runner = FakeRunner(result=_completed("this is not json\nnor is this\n"))
    _override(_env(tmp_path, runner))
    response = _post(client)

    assert response.status_code == 502


def test_worker_crash_without_output_returns_503(client, tmp_path):
    """Non-zero exit and no stdout: e.g. faster-whisper import failure."""
    runner = FakeRunner(result=_completed("", returncode=1))
    _override(_env(tmp_path, runner))
    response = _post(client)

    assert response.status_code == 503
    assert "not available" in response.json()["error"]["message"].lower()


def test_ok_true_with_empty_text_returns_502(client, tmp_path):
    runner = FakeRunner(result=_completed(json.dumps(_ok_payload(text="   ")) + "\n"))
    _override(_env(tmp_path, runner))
    response = _post(client)

    assert response.status_code == 502


# --- Missing environment -----------------------------------------------------


def test_missing_voice_venv_returns_503_without_leaking_paths(client, tmp_path):
    """Default config: .venv-voice does not exist → 503, no internal paths."""
    config = dataclasses.replace(
        settings,
        voice_python=str(tmp_path / "nonexistent" / "python"),
        voice_worker=str(tmp_path / "nonexistent" / "worker.py"),
    )
    _override(TranscriptionService(runner=_forbidden_runner(), config=config))
    response = _post(client)

    assert response.status_code == 503
    message = response.json()["error"]["message"]
    assert "not installed" in message.lower()
    # The client is told where to go (docs) but never sees an absolute path.
    assert "module-9-voice" in message
    assert str(tmp_path) not in message


# --- Isolation guarantees ----------------------------------------------------


def test_api_env_never_imports_faster_whisper():
    """The subprocess boundary keeps the STT stack out of the app venv entirely."""
    import app.services.stt  # noqa: F401 — already imported by the suite

    assert "faster_whisper" not in sys.modules
    assert "av" not in sys.modules
    assert "soundfile" not in sys.modules


def test_worker_module_needs_no_voice_deps_to_parse():
    """The worker script must stay import-safe to *parse* under the app venv.

    Its voice dependencies are imported lazily inside ``main()``/``_decode_audio``,
    so merely parsing the file never touches faster-whisper — proven here by
    compiling it with the app interpreter.
    """
    import ast
    from pathlib import Path

    worker_path = Path(__file__).resolve().parent.parent / "voice" / "transcribe_worker.py"
    tree = ast.parse(worker_path.read_text())
    # No module-level import of any voice-only dependency.
    top_level_imports = {
        alias.name
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "faster_whisper" not in top_level_imports
    assert "soundfile" not in top_level_imports
    assert "av" not in top_level_imports
    assert "numpy" not in top_level_imports

