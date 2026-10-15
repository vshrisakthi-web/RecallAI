# RecallAI

A privacy-first personal AI memory assistant. This repo currently contains:

- **`docs/`** — requirements, interface specs, module guides, and progress tracking.
- **`src/`** — React 18 + TypeScript (strict) dashboard; Timeline and Detail use the local API.
- **`extension/`** — Manifest V3 Chrome extension (capture engine + React popup).
- **`backend/`** — FastAPI ingestion and structured-memory API backed by SQLite.

---

## Frontend (dashboard + extension)

```bash
npm install
npm run dev              # local dev server
npm test                 # Vitest + RTL (86 tests)
npm run lint             # ESLint, --max-warnings 0
npm run build            # tsc + Vite production build
npm run build:extension  # assemble loadable MV3 extension -> extension/dist-extension
npm run typecheck:extension
```

Load the extension in Chrome via **Load unpacked** → `extension/dist-extension`.
In its popup, enable **Send captures to local RecallAI API** to request optional
localhost permission; sync remains off by default.

Set `VITE_API_BASE_URL` to override the dashboard's default local API URL:
`http://127.0.0.1:8000/api/v1`.

---

## Backend (Modules 3–6 — local ingestion, structured memory, and retrieval)

A FastAPI service that ingests **browser captures**, **transcript imports**, and
**manual notes**, then validates, normalizes, deduplicates, and stores them
locally. It never fetches URLs or calls external AI. **Local development only.**

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8000
```

- **Swagger UI:** <http://127.0.0.1:8000/docs>
- **Health:** `GET http://127.0.0.1:8000/api/v1/health`
- **Ingestion:** `POST /api/v1/ingest/browser`, `/transcript`, `/notes`
- **Memory API:** `GET /api/v1/memories` (search/filter/page),
  `GET /api/v1/memories/{id}`, `DELETE /api/v1/memories/{id}`,
  `POST /api/v1/memories/{id}/summary`, `GET /api/v1/sources/{id}`
- **Retrieval API:** `POST /api/v1/ask` (grounded evidence for a question),
  `POST /api/v1/memories/{id}/index`, `POST /api/v1/index`
- **Storage:** SQLite at `backend/data/recallai.db` (git-ignored; override with
  `RECALLAI_DB_PATH`). `RECALLAI_STORAGE_PATH` is only used as the legacy JSON
  import default.
- **Migrations:** run `.venv/bin/alembic upgrade head` from `backend/` before startup.
- **CORS:** only `localhost:5173` and `127.0.0.1:5173` are allowed by default;
  override with the explicit comma-separated `RECALLAI_CORS_ORIGINS` allowlist.

Run backend tests (the Module 8 harness uses the isolated Python 3.14 env):

```bash
cd backend
.venv-mcp/bin/python -m pytest -p no:warnings -q   # 671 passed, 2 skipped (all modules)
```

Use `.venv-mcp` (Python 3.14) for the full backend suite — it is the only
environment with SQLAlchemy, FastAPI, and pytest, and it supplies the shared
fixtures in `backend/tests/conftest.py` (isolated temp-dir SQLite databases,
so tests never touch the personal `recallai.db`). The default `.venv`
(Python 3.9) is for running the app, not the full suite. See `docs/testing.md`
for the full testing architecture and commands.

### Local summarization (Module 5 — complete, Tasks 5.2–5.10)

`POST /api/v1/memories/{id}/summary` summarizes a memory's stored text with a
**local Ollama model over loopback only** — no cloud provider is contacted and
no API key exists on this path. The Memory Detail screen exposes it as a
user-initiated **“Generate AI Summary”** button (never automatic).

Install and run Ollama (macOS with Homebrew; see [ollama.com](https://ollama.com)
for other platforms):

```bash
brew install ollama            # ~1.3 GB download for the 1B model below
brew services start ollama     # keeps the daemon running (loopback :11434)
ollama pull llama3.2:1b        # small default used on this repo's machine (~1.3 GB);
                               # `ollama pull llama3.2` also works with more RAM
```

Copy `backend/.env.example` to `backend/.env` and set
`RECALLAI_OLLAMA_MODEL=llama3.2:1b` to match the pulled model (the config
default is `llama3.2`, so keep them in sync). Also adjust
`RECALLAI_OLLAMA_BASE_URL` (must be a loopback host — any other URL is
rejected with 503 *before* a request is made) and
`RECALLAI_OLLAMA_TIMEOUT_SECONDS`. Launch Uvicorn **with `--env-file .env`**
so those values are picked up (the backend reads environment variables, not
the file, on its own):

```bash
cd backend && .venv/bin/uvicorn app.main:app --env-file .env --reload --port 8000
```

If Ollama or the model is unavailable, the endpoint responds 503 and
everything else keeps working. **Live-verified** on this machine: a synthetic
memory round-tripped SQLite → FastAPI → `llama3.2:1b` and returned a real
summary in ~3 s, with 404/503 error paths exercised (see
`docs/module-5-local-ai-summarization.md`).

The Gemini settings from Task 5.2 (`RECALLAI_GEMINI_*`) and the isolated
`GeminiSummarizationService` are retained with their tests but are **not used
by any runtime route**. `.env` is Git-ignored; never commit or share it. No
additional provider SDK was added because `httpx` is already a backend
dependency.

### Ask RecallAI retrieval (Module 6 — complete, Tasks 6.1–6.10)

`POST /api/v1/ask` answers a question with **grounded evidence from your local
memories — never generated prose**. The pipeline: sentence-aware chunking
(FTS5-backed `chunk_fts` index), local `nomic-embed-text` embeddings over
loopback only, a SQLite vector store with cosine search, and hybrid ranking
that fuses the semantic channel with BM25 keyword search via **Reciprocal
Rank Fusion**. The response carries ranked evidence passages (each traceable to
`memory_id`/`chunk_id`), an overall `confidence` of `none`/`weak`/`strong`,
the contributing channels, and any time window parsed from the question
("last week", "in October"); optional `from_date`/`to_date` filters (inclusive
UTC calendar days) override the parsed window. The Ask RecallAI dashboard
screen and the companion side panel call this endpoint directly — retrieval
returns evidence, and the UI explicitly does not present an answer.

Indexing is explicit (needs the embedding model, so saving a memory never
depends on it):

```bash
ollama pull nomic-embed-text        # ~274 MB, loopback-only embedding model
curl -X POST http://127.0.0.1:8000/api/v1/index                    # backfill
curl -X POST http://127.0.0.1:8000/api/v1/memories/{id}/index     # one memory
curl -X POST http://127.0.0.1:8000/api/v1/ask \
  -H 'Content-Type: application/json' \
  -d '{"question": "What did I save about vector search last week?"}'
```

Retrieval tuning lives in `.env` (`RECALLAI_RAG_*`,
`RECALLAI_EMBEDDING_*` — see `backend/.env.example` for every knob with its
default). Retrieval quality is measured by a deterministic synthetic
evaluation dataset with Recall@k / Precision@k / MRR
(`app/services/evaluation.py`, run via `pytest tests/test_evaluation.py`).
Index migrations (`20261011_0002` chunks, `20261011_0003` embeddings) ship
with the usual `alembic upgrade head`.

Import a legacy JSON store explicitly after applying migrations:

```bash
cd backend
.venv/bin/python -m app.scripts.import_json
```

The importer is repeatable and leaves the original JSON file untouched. The default
legacy file was absent during Module 4 verification, so no existing records needed
import.

Guides: [`docs/module-4-structured-memory.md`](docs/module-4-structured-memory.md)
and [`docs/module-3-ingestion-pipeline.md`](docs/module-3-ingestion-pipeline.md).

---

## Agent harness workflow (Module 8 — complete, Tasks 71–80)

A controlled, evidence-grounded workflow — **not** a chat swarm and **not** a
new framework. A single local Ollama model serves the analysis and task roles;
retrieval reuses the Module 6 hybrid service. One run flows through typed
shared state with explicit stage contracts: **router → retrieval → analysis →
task drafting → (awaiting approval)**. It retrieves evidence, analyzes it
(distinguishing facts, inferences, and unknowns), drafts an evidence-backed
checklist, and persists approved tasks **only** after an explicit user action.

### Workflow API

```bash
# 1) Run a workflow. A task objective returns drafts in awaiting_approval
#    and persists NOTHING.
curl -X POST http://127.0.0.1:8000/api/v1/workflow \
  -H 'Content-Type: application/json' \
  -d '{"question": "create tasks from my RAG notes"}'

# 2) Approve / edit / reject the returned run_id. This is the ONLY call that
#    persists tasks. An LLM "approval" is never valid — the decision must come
#    from this explicit request.
curl -X POST http://127.0.0.1:8000/api/v1/workflow/{run_id}/approve \
  -H 'Content-Type: application/json' \
  -d '{"decision": "approve"}'
```

- **Objectives:** `search`, `summarize`, `analyze_learning`, `create_tasks`.
  The deterministic router maps the question to one of these, or returns a
  clarification when the intent is ambiguous. It never lets the model choose
  arbitrary tools/actions.
- **Response:** `run_id`, `objective`, `status`, `findings`, `evidence`
  (each traceable to a `chunk_id`), `task_drafts` (`status="draft"`), `errors`,
  and a sanitized `trace` (stage, status, duration, attempt count).
- **Approval statuses:** `approve` validates and persists the drafts → run
  `completed`; `reject` persists nothing → run `rejected`; `edit` re-validates
  the submitted drafts (source ids must match retrieved evidence, caps apply)
  before persisting. Unknown/stale `run_id` → 404; a wrong state or replayed
  decision → 409; an invalid edit → 422; a storage failure → 503 (the run
  stays `awaiting_approval`).

### Approval & persistence boundary (security)

Task drafting is **in-memory only**. Approved drafts are stored as JSON in the
existing `tasks.input_reference` column (`task_type="agent_task_draft"`) — no
migration and no schema change. Persistence happens only inside the approval
path, in a single transaction (all-or-nothing). Model output, retrieved
memories, or any generated text — including a claim that "the user approved" —
can never authorize a write.

### Resilience (Task 78)

Every model/retrieval call runs through bounded retries (transient failures
only; permanent validation/schema/contract errors are never retried) and a
per-stage wall-clock timeout plus a whole-run budget. Traces record the true
attempt count. Failures are reported (run `failed`) with safe, bounded
messages — never silently turned into success.

### Configuration

`RECALLAI_AGENT_*` env vars tune the harness limits (query length, evidence
count/budget, task count/caps, stage timeout, total budget, max attempts, max
errors) — see `backend/.env.example`. The workflow uses the same loopback
Ollama settings as Module 5/6 (`RECALLAI_LLM_*`, `RECALLAI_OLLAMA_*`).

### Frontend

The **Workflow Review** screen (`/workflow`) submits a question, renders the
proposed drafts with their supporting evidence, and provides explicit
**Approve** / **Reject** actions that call the approval endpoint. It shows
success, validation, and failure states, and never treats returned text as
approval.

### Limitations (local, single-user)

- The pending-run registry is **in-process**: pending approvals are lost if the
  server restarts (persisted tasks are unaffected).
- There is **no authentication**; the app is local, single-user development.
  Approval is an application-level action boundary, not multi-user
  authorization.
- Automated tests are deterministic and offline (fake embedding/Ollama
  transports, isolated SQLite). End-to-end coverage lives in
  `backend/tests/test_e2e_workflow.py`; approval-boundary tests in
  `backend/tests/test_approval.py`; resilience in
  `backend/tests/test_resilience.py`.

Design of record: [`docs/module-8-agent-harness.md`](docs/module-8-agent-harness.md).
