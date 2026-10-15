"""Speech-to-text endpoint (Module 9, Task 82).

``POST /api/v1/voice/transcribe`` accepts one multipart audio upload and
returns the transcript the **local** model produced. It is the input half of
the voice pipeline: the client puts the transcript into the ordinary Ask box,
so nothing here queries memories, creates records, or bypasses the approval
boundary — transcription produces text, and text is then handled by the exact
same code path a typed question would take.

Privacy posture, matching the rest of this backend:

* The worker runs in an isolated venv on this machine; audio and transcript
  never leave the device (no hosted STT is configured or possible).
* The upload is deleted immediately after the worker returns (see
  ``TranscriptionService.transcribe``'s ``finally`` block).
* Neither the transcript nor any audio content is logged — only byte counts,
  durations, and outcomes.

HTTP status (errors use the shared envelope via the global handlers):
  - 200        transcription succeeded
  - 422        unusable audio (empty, oversize, unsupported, or no speech)
  - 502        the worker crashed or spoke an unreadable protocol
  - 503        the voice environment is not installed / model failed to load
  - 504        the worker exceeded RECALLAI_VOICE_TIMEOUT_SECONDS (and was killed)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.deps import get_transcription_service
from app.core.config import settings
from app.core.request_id import get_request_id
from app.schemas.voice import TranscribeResponse
from app.services.stt import (
    TranscriptionInputError,
    TranscriptionService,
    TranscriptionTimeoutError,
    TranscriptionUnavailableError,
    TranscriptionWorkerError,
)

router = APIRouter(prefix="/voice", tags=["voice"])
logger = logging.getLogger("recallai.voice")

# Multipart part header we read at a time when bounding the upload in memory.
_CHUNK_BYTES = 64 * 1024


def _read_bounded(file: UploadFile) -> bytes:
    """Read at most ``max_voice_audio_bytes`` + 1 bytes from the upload.

    Starlette has already spooled the multipart body to a temp file on disk;
    this stops *pulling* it into memory the moment the limit is exceeded, so an
    oversized upload costs one bounded read rather than process-sized RAM.
    """
    limit = settings.max_voice_audio_bytes
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = file.file.read(_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise TranscriptionInputError(
                f"The audio exceeds the {limit // (1024 * 1024)} MB upload limit."
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/transcribe", response_model=TranscribeResponse)
def transcribe(
    file: UploadFile = File(...),
    service: TranscriptionService = Depends(get_transcription_service),
) -> TranscribeResponse:
    """Transcribe one audio upload with the local speech model.

    The uploaded bytes are read once, validated (content-type allowlist plus
    magic-byte sniffing), written to a private temp file for the worker, and
    always deleted before this handler returns. Declared sync on purpose: the
    worker subprocess can run for up to ``voice_timeout_seconds``, and FastAPI
    runs sync handlers in a threadpool instead of blocking the event loop —
    the same convention every other route in this app follows.
    """
    request_id = get_request_id()

    try:
        audio = _read_bounded(file)
        result = service.transcribe(audio, file.content_type or "")
    except TranscriptionInputError as exc:
        # Unusable audio is a client problem; the message is already safe.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TranscriptionTimeoutError:
        logger.warning(
            "voice worker timed out (bytes=%d)", len(audio), extra={"request_id": request_id}
        )
        raise HTTPException(
            status_code=504,
            detail="Transcription took too long and was stopped.",
        ) from None
    except TranscriptionUnavailableError as exc:
        logger.warning(
            "voice worker unavailable: %s", exc, extra={"request_id": request_id}
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except TranscriptionWorkerError:
        # Real cause stays in the server log; the client gets a safe message.
        logger.exception("voice worker failed", extra={"request_id": request_id})
        raise HTTPException(
            status_code=502,
            detail="Transcription failed unexpectedly. Please try again.",
        ) from None

    return TranscribeResponse(
        transcript=result.transcript,
        language=result.language,
        duration_seconds=result.duration_seconds,
        model=result.model,
    )
