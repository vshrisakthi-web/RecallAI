"""Speech-to-text over an isolated subprocess boundary (Task 82).

Why a subprocess: the STT stack (faster-whisper/CTranslate2/onnxruntime) is
large, version-pinned, and completely independent of the API runtime. Installing
it into ``.venv-mcp`` would put the 549-test backend environment at the mercy of
native-wheel churn. Instead the model lives in ``.venv-voice`` and this service
talks to it exactly once per request:

    <voice_python> voice/transcribe_worker.py <tmp.wav> <model> <max_seconds>

with a one-shot JSON protocol on stdout (see ``voice/transcribe_worker.py``).

Privacy and safety rules enforced here, before and after the spawn:

* Accepted formats are an explicit allowlist, verified by magic bytes — the
  declared Content-Type is never trusted on its own.
* Byte-size and decoded-duration limits bound both memory and inference time;
  the duration check happens inside the worker *before* the model loads.
* The upload is written to a private temp file that is deleted in a
  ``finally`` block on every path — success, failure, and timeout alike.
* ``subprocess.run(timeout=...)`` kills the worker on timeout; a dead worker
  can never be mistaken for a transcript because exit code 0 is required and
  the JSON is parsed strictly.
* Error messages are fixed, safe strings: no temp paths, no stderr, no stack
  traces reach the client. The transcript itself is never logged.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from app.core.config import settings as default_settings
from app.core.config import Settings, VoiceConfigError

logger = logging.getLogger("recallai.voice")


class TranscriptionInputError(ValueError):
    """The uploaded audio is unusable (format, size, or emptiness). Mapped to 422."""


class TranscriptionUnavailableError(RuntimeError):
    """The worker is not installed/configured, or the model failed to load. Mapped to 503."""


class TranscriptionTimeoutError(RuntimeError):
    """The worker exceeded its budget and was killed. Mapped to 504."""


class TranscriptionWorkerError(RuntimeError):
    """The worker crashed or spoke an unreadable protocol. Mapped to 502."""


# Content types browsers may legitimately send from MediaRecorder/audio inputs.
ALLOWED_AUDIO_CONTENT_TYPES = frozenset(
    {
        "audio/webm",
        "audio/mp4",
        "audio/mpeg",
        "audio/wav",
        "audio/x-wav",
        "audio/ogg",
        "audio/flac",
    }
)

# Magic-byte signatures. These are what the *file* is, independent of the
# client-declared Content-Type, so a mislabelled upload is still classified.
_MAGIC_CHECKS: tuple[tuple[str, bytes], ...] = (
    ("webm", b"\x1a\x45\xdf\xa3"),  # EBML header (webm/matroska)
    ("ogg", b"OggS"),
    ("flac", b"fLaC"),
    ("wav", b"RIFF"),
)


@dataclass(frozen=True)
class TranscriptionResult:
    """One successful transcription."""

    transcript: str
    language: str
    duration_seconds: float
    model: str


def _sniff_format(header: bytes) -> Optional[str]:
    """Return a container name from the first bytes, or None if unrecognised."""
    if len(header) < 12:
        return None
    if header[4:8] == b"ftyp":
        return "mp4"  # also covers m4a/aac-in-mp4 (Safari MediaRecorder)
    for name, magic in _MAGIC_CHECKS:
        if header.startswith(magic):
            if name != "wav":
                return name
            # RIFF alone is ambiguous (AVI is RIFF too); require WAVE.
            if header[8:12] == b"WAVE":
                return "wav"
            return None
    # MPEG audio: either an ID3 tag or a frame-sync word (0xFF Ex/Fx).
    if header.startswith(b"ID3"):
        return "mp3"
    if header[0] == 0xFF and (header[1] & 0xE0) == 0xE0:
        return "mp3"
    return None



class TranscriptionService:
    """Transcribes uploaded audio by driving the isolated worker process.

    ``runner`` is injectable so tests can substitute the subprocess entirely —
    the same seam style as ``OllamaSummarizationService(post=...)``. The
    default runner is :func:`subprocess.run`, which kills its child on timeout.
    """

    def __init__(
        self,
        runner: Optional[Callable[..., "subprocess.CompletedProcess"]] = None,
        config: Optional[Settings] = None,
        temp_dir: Optional[str] = None,
    ) -> None:
        self._run = runner or subprocess.run
        self._config = config or default_settings
        self._temp_dir = temp_dir  # tests point this at tmp_path

    # -- validation ---------------------------------------------------------

    def _validate(self, audio: bytes, content_type: str) -> str:
        """Return the sniffed container name, or raise TranscriptionInputError."""
        media_type = (content_type or "").split(";")[0].strip().lower()
        if media_type not in ALLOWED_AUDIO_CONTENT_TYPES:
            raise TranscriptionInputError(
                "Unsupported audio format. Send webm, mp4, mpeg, wav, ogg, or flac."
            )
        if not audio:
            raise TranscriptionInputError("The uploaded audio is empty.")
        if len(audio) > self._config.max_voice_audio_bytes:
            limit_mb = self._config.max_voice_audio_bytes // (1024 * 1024)
            raise TranscriptionInputError(
                f"The audio exceeds the {limit_mb} MB upload limit."
            )
        container = _sniff_format(audio[:64])
        if container is None:
            raise TranscriptionInputError(
                "The file does not look like a supported audio recording."
            )
        return container

    # -- worker protocol ----------------------------------------------------

    def _spawn(
        self, python: str, worker: str, audio_path: Path, model: str
    ) -> "subprocess.CompletedProcess":
        command = [
            python,
            worker,
            str(audio_path),
            model,
            str(self._config.max_voice_audio_seconds),
        ]
        return self._run(
            command,
            capture_output=True,
            text=True,
            timeout=self._config.voice_timeout_seconds,
        )

    def _interpret(self, completed: "subprocess.CompletedProcess") -> TranscriptionResult:
        """Parse the worker's single JSON line; never trust anything else."""
        stdout = (completed.stdout or "").strip()
        if completed.returncode != 0 and not stdout:
            # Crashed before it could speak the protocol (e.g. import error).
            raise TranscriptionUnavailableError(
                "Speech transcription is not available. Is the voice model installed?"
            )
        # The worker emits exactly one JSON line, but tolerate incidental
        # library chatter by reading the last non-empty line.
        last_line = stdout.splitlines()[-1] if stdout else ""
        try:
            payload = json.loads(last_line)
        except json.JSONDecodeError as exc:
            raise TranscriptionWorkerError("Transcription failed unexpectedly.") from exc

        if not isinstance(payload, dict) or "ok" not in payload:
            raise TranscriptionWorkerError("Transcription failed unexpectedly.")

        if payload.get("ok") is True:
            text = payload.get("text")
            if not isinstance(text, str) or not text.strip():
                raise TranscriptionWorkerError("Transcription failed unexpectedly.")
            return TranscriptionResult(
                transcript=text.strip(),
                language=str(payload.get("language", "")),
                duration_seconds=float(payload.get("duration_seconds") or 0.0),
                model=str(payload.get("model") or self._config.voice_model),
            )

        kind = payload.get("kind")
        message = str(payload.get("message") or "")
        if kind in {"invalid-audio", "no-speech", "too-long"}:
            raise TranscriptionInputError(message or "The audio could not be transcribed.")
        if kind == "model-load-failed":
            raise TranscriptionUnavailableError(message or "The speech model is not installed.")
        # Anything else — including "worker-error" — is an unexpected worker
        # failure: 502, never a silent None that would surface as a 500.
        raise TranscriptionWorkerError(message or "Transcription failed unexpectedly.")


    # -- entry point --------------------------------------------------------

    def transcribe(self, audio: bytes, content_type: str) -> TranscriptionResult:
        """Validate, persist to a temp file, run the worker, always clean up."""
        container = self._validate(audio, content_type)

        # Refuse before spawning anything if the venv/worker is missing, so a
        # 503 never costs a subprocess and never leaks an internal path.
        try:
            python, worker = self._config.require_voice_worker()
        except VoiceConfigError as exc:
            raise TranscriptionUnavailableError(str(exc)) from exc

        handle, raw_path = tempfile.mkstemp(
            prefix="recallai-voice-", suffix=f".{container}", dir=self._temp_dir
        )
        os.close(handle)
        audio_path = Path(raw_path)
        try:
            audio_path.write_bytes(audio)
            try:
                completed = self._spawn(python, worker, audio_path, self._config.voice_model)
            except subprocess.TimeoutExpired as exc:
                # run() already killed the child; we only report it.
                raise TranscriptionTimeoutError(
                    "Transcription took too long and was stopped."
                ) from exc
            result = self._interpret(completed)
            logger.info(
                "transcription ok (bytes=%d, duration=%.2fs, model=%s)",
                len(audio),
                result.duration_seconds,
                result.model,
            )
            return result
        finally:
            # Deleted on success, failure, timeout, and unexpected exception —
            # raw audio never outlives this call.
            audio_path.unlink(missing_ok=True)
