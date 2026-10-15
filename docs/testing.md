# RecallAI — Testing Guide

This document describes the automated testing foundation: how tests are
organized, which environment runs them, the shared fixtures, and the exact
commands to reproduce every suite. All ordinary tests are **deterministic and
offline** — no live LLM, no Ollama, no network, no paid APIs, and no access to
the personal RecallAI memory database.

---

## 1. Environments

RecallAI has several isolated Python environments. Use the right one per suite:

| Environment | Python | Purpose | Use for |
|---|---|---|---|
| `.venv-mcp` | **3.14** | Full backend suite | **All backend pytest runs** — only env with SQLAlchemy 2.0 + FastAPI 0.111 + pytest 8.2 |
| `.venv` | 3.9 | Running the app / API server | `uvicorn app.main:app`, not the full suite |
| `.venv-voice` | 3.14 | Voice worker (STT/TTS) | Voice smoke tests only |
| `.venv-ft` | 3.12 | ML fine-tuning (Module 9, Task 88) | LoRA training/eval only |

**Why `.venv-mcp`?** The earlier `.venv` (Python 3.9) is missing `sqlalchemy`,
which is why running the suite under system `python3` produced import errors.
`.venv-mcp` is the only environment with the complete dependency set, so the
full backend suite must run there.

```bash
cd backend
.venv-mcp/bin/python -m pytest -p no:warnings -q   # 671 passed, 2 skipped
```

---

## 2. Backend tests (`backend/tests/`)

Covered components (all offline, deterministic):

- **Ingestion** (`test_ingestion*`, `test_notes.py`, `test_transcript.py`) —
  input transformation, validation, deduplication, malformed/missing fields.
- **Structured memory & storage** (`test_memory_api.py`, `test_storage_errors.py`,
  `test_repository.py`) — CRUD, source identifiers, error propagation.
- **Retrieval / RAG** (`test_retrieval*`, `test_hybrid_retrieval.py`,
  `test_keyword_search.py`, `test_vector_store.py`) — matching records, empty
  query/corpus, no-match cases, stable ranking, source metadata.
- **Orchestration & agents** (`test_orchestrator.py`, `test_workflow_schemas.py`,
  `test_e2e_workflow.py`, `test_approval.py`, `test_resilience.py`) — workflow
  transitions, agent failures, tool-argument validation, approval boundaries.
- **Cross-boundary integration (Task 92)** (`test_integration_lifecycle.py`) —
  walks one memory through the *real* capture → persist → index → retrieve →
  delete path (real routes + real services + the disposable SQLite DB), asserting
  idempotent ingestion, 422 validation leaves no partial rows, cascade deletion of
  chunks/vectors, deleted memories never reappearing in retrieval, and that an
  unrelated query returns no evidence. Only the embedding model boundary is faked
  (deterministic local transport; no network/model). Workflow (Task 92 D) and MCP
  (Task 92 E) are covered by `test_e2e_workflow.py` and `test_mcp*` respectively
  and are intentionally not duplicated here.
- **MCP** (`test_mcp*`) — tool registration, argument schemas, error propagation.
- **Voice** (`test_voice_api.py`, `test_transcript.py`) — injectable
  subprocess runner; no model download or worker process in tests.
- **Local AI / summarization** (`test_summary_api.py`) — Ollama provider boundary
  is substituted; no running model required.
- **Classification (Module 9)** — `test_classification_baseline.py` (Task 87),
  `test_classification_lora.py` (Task 88, real smoke test in `.venv-ft`),
  `test_classification_task89.py` (Task 89), `test_classification_task87_num_predict.py`
  (Task 90). The baseline/task89 tests run under `.venv-mcp`; the LoRA tests
  require `.venv-ft`.

Model-dependent behaviour is tested with **deterministic mocks / dependency
injection** (fake providers, stub HTTP clients, injectable runners). Real-model
smoke tests are isolated and explicitly marked (skipped when the ML env is
absent). Mocked results are never presented as real model performance.

### Shared fixtures — `backend/tests/conftest.py`

- `storage_path` — an isolated JSON file in a temp dir (legacy import tests).
- `database_path` — a per-test SQLite path under `tmp_path`.
- `database_engine` — creates a **disposable** engine and runs Alembic
  `upgrade head` against it (never the personal DB), then disposes.
- `repository` — a `MemoryRepository` bound to that isolated engine.
- `client` — a FastAPI `TestClient` with `get_repository` overridden to the
  isolated repository; overrides are cleared on teardown.

Every DB-backed test therefore gets a **fresh, migrated, temp-dir SQLite
database** and can never touch `backend/data/recallai.db` or cross-contaminate
other tests.

---

## 3. Frontend tests (Vitest + React Testing Library)

```bash
npm test            # 86 tests across 14 files
npm run lint        # ESLint, --max-warnings 0
npm run typecheck:extension
```

Covers the dashboard (`src/test/`), the Chrome extension popup
(`src/test/ExtensionPopup.test.tsx`), and extension background messaging
(`extension/tests/messages.test.ts`). Uses jsdom + Testing Library; no network.

---

## 4. Full verification (one command each)

```bash
# Backend (all modules)
cd backend && .venv-mcp/bin/python -m pytest -p no:warnings -q

# Frontend + extension
npm test
```

Expected: **676 passed, 2 skipped** (backend) and **86 passed** (frontend), both
exit code 0. The 2 backend skips are real-model smoke tests that require the
ML environment / a running model and are intentionally environment-gated.

---

## 5. Known non-Task-91 caveats

- Do **not** run the backend suite under system `python3` or `.venv`
  (Python 3.9) — `sqlalchemy` is absent there and collection fails. This is an
  environment-selection issue, not a code defect.
- `.venv-voice` (Python 3.14) does not expose a working `bin/python` launcher in
  this checkout; voice worker smoke tests are run through the app's injectable
  runner instead.
