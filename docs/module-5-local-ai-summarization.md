# Module 5 — Local AI Summarization

Status: **complete (Tasks 5.2–5.10)**. Last verified 2026-10-11 on macOS
(Apple Silicon) with Ollama 0.40.3 and model `llama3.2:1b`.

## What was built

| Piece | Where |
| --- | --- |
| Summary endpoint (Task 5.5) | `POST /api/v1/memories/{memory_id}/summary` in `backend/app/api/routes/memories.py` |
| Local Ollama provider (Task 5.6) | `OllamaSummarizationService` in `backend/app/services/summarization.py` |
| Hosted Gemini provider (Tasks 5.2–5.3, **retired from runtime**) | same file, `GeminiSummarizationService` — kept with tests, never imported by any route/dep |
| Config knobs (loopback-enforced) | `Settings` in `backend/app/core/config.py` |
| Frontend API client (Task 5.8) | `summarizeMemory()` + `MemorySummary` in `src/lib/memoriesApi.ts` |
| Memory Detail UI (Task 5.8) | “Generate AI Summary” section in `src/pages/MemoryDetail.tsx` |

The endpoint takes **only the memory's normalized text** and sends it to
`POST {RECALLAI_OLLAMA_BASE_URL}/api/chat` (`stream: false`) with a fixed
system instruction that treats the captured text as untrusted data
(prompt-injection safeguard). No credentials are sent to Ollama, and the base
URL is validated to be loopback (`localhost`, `127.0.0.1`, `::1`) **before any
request is made** — a non-loopback URL returns 503 with nothing leaving the
device.

## Environment variables (`backend/.env`, Git-ignored)

```bash
RECALLAI_OLLAMA_BASE_URL=http://127.0.0.1:11434   # loopback only
RECALLAI_OLLAMA_MODEL=llama3.2:1b                 # must match a pulled model
RECALLAI_OLLAMA_TIMEOUT_SECONDS=30
RECALLAI_MAX_SUMMARY_INPUT_CHARS=30000
```

The config default for the model is `llama3.2`; this machine uses
`llama3.2:1b` (≈1.3 GB), so `.env` pins it explicitly. The backend reads
**environment variables** at startup — start Uvicorn with `--env-file .env`
or the file's values are ignored.

## Running everything (verified commands)

```bash
# 1. Ollama daemon + model (macOS, once)
brew install ollama
brew services start ollama   # persists across shells; listens on 127.0.0.1:11434
ollama pull llama3.2:1b

# 2. Backend
cd backend
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --env-file .env --reload --port 8000

# 3. Frontend (separate shell)
cd /Users/shrisakthi/projects/RecallAI && npm run dev   # http://127.0.0.1:5173
```

## Generating a summary (UI or API)

UI: open **Timeline → a memory → “Generate AI Summary”**. The button shows a
loading state, prevents duplicate requests, displays the returned summary and
the actual model id, and clears stale results when you navigate to another
memory. Summarization is **user-initiated only** — nothing is summarized
automatically.

API:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/memories/<memory_id>/summary \
  -H 'Content-Type: application/json' -d '{}'
# → {"memory_id": "...", "summary": "...", "model": "llama3.2:1b"}
```


## Live verification results (Task 5.7, 2026-10-11)

- Direct Ollama inference: synthetic prompt → real text from `llama3.2:1b`.
- Full pipeline with a synthetic memory (`mem_e35bfbd36b80a75901724b77`,
  photosynthesis text — no personal data): ingest → SQLite → summary endpoint
  returned a real 4-bullet summary in ~3.3 s with correct `memory_id`,
  `summary`, and `model` fields.
- Error paths live-tested: missing memory → 404 `NOT_FOUND` envelope; repeat
  request → 200 with a fresh summary; Ollama daemon on a dead loopback port →
  503 `PROVIDER_NOT_CONFIGURED` with a safe generic message; validation
  failure → 422 envelope. `X-Request-ID` is echoed in envelopes and headers.

## Test results (Task 5.9)

- Backend: full suite **132 passed** (mocked; does not need a running daemon).
  Focused files: `tests/test_ollama_summarization.py` (19),
  `tests/test_summary_api.py` (14) — payload shape, loopback enforcement,
  credential-free requests, client-supplied API-key ignored, input limits,
  404/503/504/502 mappings, malformed responses.
- Frontend: **54 passed** (`npm test`) including 4 Memory Detail summary tests
  (success + model display, loading + duplicate-click prevention, error
  message + retry, stale-response discard across navigation). `npm run lint`
  clean, `npx tsc -b --noEmit` clean, `npm run build` succeeds.

## Privacy properties (verified by code inspection + tests)

- The active summary path uses Ollama only; no runtime route imports the
  Gemini service, and no browser request carries an API key.
- Non-loopback Ollama URLs are rejected before transport (unit-tested, no
  network).
- Memory text is not logged (the summarization service has no logger) and
  error envelopes expose no secrets or stack traces.
- External captured text is passed as untrusted data under a fixed system
  instruction.
- Chrome extension capture-consent controls were not touched by Module 5.

## Known limitations / manual steps remaining

- **Fully offline verification not performed** — that requires disabling
  internet on this machine, which was left to the user. Verification levels:
  mocked ✓, live local inference ✓, end-to-end backend ✓; UI click-through is
  manual (no browser-automation tooling in this repo), offline is pending.
- First summary after a daemon restart pays a one-off model-load latency
  (seconds); the default 30 s timeout covers it.
- Summaries are not cached; each click re-runs the model (user-initiated by
  design).
- `llama3.2:1b` is a small model — summaries are decent but occasionally
  verbose; bump `RECALLAI_OLLAMA_MODEL` to `llama3.2` for better quality if
  RAM allows.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| 503 `PROVIDER_NOT_CONFIGURED` instantly | daemon down, model not pulled, or wrong model name | `brew services start ollama`; `ollama list`; set `RECALLAI_OLLAMA_MODEL` to a pulled model |
| 503 after starting uvicorn without `--env-file .env` | model name falls back to config default `llama3.2` | restart with `--env-file .env` |
| 504 | model too slow / timeout too low | raise `RECALLAI_OLLAMA_TIMEOUT_SECONDS` |
| Frontend “Could not reach the local RecallAI server” | backend not running | start uvicorn on 127.0.0.1:8000 |
| `could not connect to ollama server` from CLI | daemon not up | `brew services start ollama` or `ollama serve` |
