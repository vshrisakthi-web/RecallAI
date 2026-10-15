"""Request/response models for speech-to-text (Module 9, Task 82).

The upload itself is a multipart file (FastAPI ``UploadFile``), not JSON, so
only the *response* is modelled here. Like ``AskResponse``, the response
carries raw model output with no invented fields: the transcript is exactly
what the local speech model produced, and it is the client's job to review it
before submitting it as a question. Nothing here references remote services.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TranscribeResponse(BaseModel):
    """One successful transcription.

    ``duration_seconds`` is the decoded audio length (bounded by
    ``RECALLAI_MAX_VOICE_AUDIO_SECONDS``), not wall-clock processing time —
    it exists so the UI can sanity-check what it recorded. ``language`` is the
    BCP-47-ish code the model detected (e.g. ``en``); the model auto-detects,
    so an empty string means detection was inconclusive rather than an error.
    """

    transcript: str = Field(min_length=1)
    language: str = ""
    duration_seconds: float = Field(ge=0.0)
    model: str
