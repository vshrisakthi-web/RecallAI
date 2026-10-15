# Module 9 – Voice Input & Speech-to-Text

## Overview

This module provides voice input support and asynchronous speech-to-text transcription for the RecallAI platform. It consists of:

- **VoiceInput** – React component that manages the microphone lifecycle (request permission, record, process, display transcript).
- **TranscribeWorker** – Subprocess-bound worker that runs Faster‑Whisper locally, enforces size/format limits, and returns structured JSON.
- **TranscriptionService** – Injected service that wires the worker into the FastAPI request pipeline.
- **Transcription API** – `POST /api/v1/voice/transcribe` endpoint accepting multipart audio uploads.

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Frontend   │────▶│  VoiceInput      │────▶│  TranscribeWorker│
│  (React)    │     │  (state machine) │     │  (subprocess)   │
└─────────────┘     └──────────────────┘     └─────────────────┘
                              │                        │
                              ▼                        ▼
                       ┌──────────────────┐     ┌─────────────────┐
                       │  Transcription   │◀────│  Transcription  │
                       │  Service         │     │  API (FastAPI)  │
                       └──────────────────┘     └─────────────────┘
```

## Key Components

### VoiceInput (frontend)
- State machine: `idle → requesting-permission → recording → processing → success | error`
- Displays a live transcript preview (updated after successful transcription).
- Handles cancellation, mute, and permission denial gracefully.
- Uses `aria-live="polite"` and proper focus management.

### TranscribeWorker (backend)
- Runs as a standalone subprocess (isolated from the main RecallAI server).
- Accepts arguments: `audio_path`, `model_name`, `max_seconds`.
- Validates audio format (WAV, MP4, WebM, OGG, FLAC) and rejects unsupported types.
- Enforces size limits (≤10 MB) and duration caps (≤120 s).
- On failure, returns a structured error with `kind` (e.g., `unsupported`, `too-long`, `no-speech`, `model-load-failed`).
- Outputs a single JSON line on stdout: `{"ok":true,"text":"..."}` or `{"ok":false,"kind":"..."}`.

### TranscriptionService (injection)
- Wired into `app.dependencies` via `get_transcription_service()`.
- Provides `run(transcribe_fn, request)` that handles subprocess lifecycle, timeouts (120 s), and cleanup.

### Transcription API
- Endpoint: `POST /api/v1/voice/transcribe`
- Body: multipart/form-data with `audio` (file) and `model` (optional, defaults to `tiny`).
- Response: `{"ok":true,"text":"...", "language":"en", "duration_seconds":1.89, "model":"tiny"}`
- Errors: `422 Unprocessable Entity` for bad requests, `502 Bad Gateway` when the worker fails, `503 Service Unavailable` when the worker isn't running.

## Setup

```bash
# Create isolated Python 3.12 virtual environment
python3.12 -m venv .venv-voice

# Install voice dependencies (all have wheels for macOS arm64)
.venv-voice/bin/pip install -r requirements-voice.txt

# Pre-warm the tiny model (first run only)
.venv-voice/bin/python -c "from faster_whisper import WhisperModel; WhisperModel('tiny', device='cpu', compute_type='int8')"
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `RECALLAI_VOICE_PYTHON` | `backend/.venv-voice/bin/python` | Path to the voice venv interpreter |
| `RECALLAI_VOICE_MODEL` | `tiny` | Faster‑Whisper model name (tiny ≈ 75 MB, base ≈ 145 MB) |
| `RECALLAI_VOICE_MAX_AUDIO_BYTES` | `10485760` | Max upload size (10 MB) |
| `RECALLAI_VOICE_MAX_DURATION` | `120` | Max transcription length (seconds) |
| `RECALLAI_VOICE_TIMEOUT_SECONDS` | `120` | Subprocess timeout |

## Testing

All voice-related tests are in `tests/test_voice_api.py` (22 tests). They cover:
- Successful transcription with a mocked worker
- Unsupported audio formats (WebM, MP4, etc.) → 422
- Empty / malformed audio → 422
- Oversized audio (>10 MB) → 422
- Too long audio (>120 s) → 502
- Invalid model selection → 502
- Timeout scenarios → 504
- Malformed stdout from worker → 502
- Missing voice worker → 503

Run with:
```bash
.venv-voice/bin/pytest tests/test_voice_api.py -v
```

## License

MIT