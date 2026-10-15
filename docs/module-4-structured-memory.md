# RecallAI Module 4 — Structured Memory

Module 4 replaces the JSON file as the backend's active store with local SQLite, keeps the Module 3 ingestion endpoints, and connects the Timeline and Detail screens to those APIs. It adds no embeddings, cloud calls, or LLM behavior.

## Architecture

- `backend/app/database/models.py` maps `Source`, `Memory`, `Conversation`, and `Task` with SQLAlchemy 2.x.
- `backend/app/database/session.py` creates synchronous SQLite engines, enables foreign keys, and supports an explicit path for isolated tests.
- `backend/app/migrations/versions/20261011_0001_structured_memory.py` creates the schema and FTS5 table/triggers when the SQLite build supports FTS5.
- `backend/app/repositories/sqlite_store.py` owns source/memory writes, deduplication, search, filtering, pagination, lookups, and deletion.
- `backend/app/services/ingestion.py` remains the canonical Module 3 normalization/hash/orchestration path. FastAPI dependency wiring now supplies the SQLite repository.
- `src/lib/memoriesApi.ts` maps the backend contract into existing UI models. Timeline and Detail use the API directly; other mock-AI/demo screens remain isolated mock views.

A source is reused for records with the same source type and URL. A memory is one captured version/content item. Multiple memories can reference a source. Deleting a memory does not delete its source; the source endpoint reports `memory_count: 0` when it has no remaining memories.

## Database and migrations

Default development database: `backend/data/recallai.db`. The complete `backend/data/` directory and SQLite database/journal/WAL/SHM files are ignored by Git. Override the file with `RECALLAI_DB_PATH`.

After installing `backend/requirements.txt`, create or update the database with:

```bash
cd backend
.venv/bin/alembic upgrade head
```

Use `alembic current`, `alembic heads`, or any SQLite browser to inspect it. Production-style application startup does not call `create_all()`; apply the migration before starting FastAPI. `init_db(engine)` is a test helper only.

The first revision creates:

- `sources`: source type, canonical URL, domain, title, JSON metadata, identity key, timestamps.
- `memories`: source FK, title, normalized body, content hash, unique dedup key, captured/ingested timestamps, request ID, capture type, selected text/context, extraction state/note, JSON metadata.
- `conversations` and `tasks`: minimal placeholders only; no conversation engine or task queue.
- `memories_fts`: FTS5 title/body/source-title/domain index with insert/update/delete synchronization triggers, when available.

SQLite foreign-key enforcement is enabled for every application/test engine. If FTS5 cannot be created, text search uses parameterized, case-insensitive `LIKE` predicates instead.

## JSON import

The legacy path is still `backend/data/ingested.json` (or `RECALLAI_STORAGE_PATH`), but the live app no longer uses it. Before the first development migration, that default JSON file was checked and did **not** exist, so there were no records to import. The original JSON repository/file are retained; no file is automatically removed.

To import a legacy file after applying migrations:

```bash
cd backend
.venv/bin/python -m app.scripts.import_json
.venv/bin/python -m app.scripts.import_json --json-file /path/to/ingested.json
```

The command reports `read`, `imported`, `duplicates`, and `skipped` counts, validates each canonical record, is safe to rerun, and never writes to or deletes the JSON source.

## Deduplication and timestamps

The preserved Module 3 identity is `source_type + source_url + capture_type + SHA256(normalized_text)`; title is excluded. An identical retry returns the existing memory (`200`, `duplicate: true`). Changed content from the same page creates a new memory linked to the same source. Selection and full-page captures remain distinct. URL-less notes get individual source rows; identical note content still follows the existing Module 3 content-based dedup rule.

Incoming timestamps must be timezone-aware and are normalized to UTC. `from_date` and `to_date` are inclusive UTC calendar dates: the lower bound is midnight at `from_date`, and the upper bound is exclusive midnight after `to_date`.

## API

Base path: `http://127.0.0.1:8000/api/v1`. All errors keep the Module 3 envelope and `X-Request-ID` header.

| Method | Endpoint | Behavior |
| --- | --- | --- |
| `GET` | `/health` | Liveness/version (`0.4.0`). |
| `POST` | `/ingest/browser` | Browser/selection capture; `201` new, `200` duplicate. |
| `POST` | `/ingest/transcript` | Transcript text and optional source metadata; `201`/`200`. |
| `POST` | `/ingest/notes` | Manual note; URL is optional; `201`/`200`. |
| `GET` | `/memories` | Search/list/filter with pagination. |
| `GET` | `/memories/{memory_id}` | Canonical saved memory plus its source. |
| `DELETE` | `/memories/{memory_id}` | Delete one memory; retain its source; `404` if missing. |
| `GET` | `/sources/{source_id}` | Source fields plus current `memory_count`. |

List query parameters: `q` (max 256 chars), `from_date`, `to_date` (`YYYY-MM-DD`), `domain` (exact normalized hostname or IP), `source_type` (`browser`, `transcript`, `note`), `page` (default 1), and `page_size` (default 25, max 100). Filters combine. Results sort by relevance when searching, then capture time and ID deterministically; without a search, newest capture time and ID first. Empty/punctuation-only `q` behaves as no text filter.

Example list request:

```bash
curl 'http://127.0.0.1:8000/api/v1/memories?q=sqlite&from_date=2026-10-01&to_date=2026-10-11&domain=docs.example&source_type=browser&page=1&page_size=12'
```

List response shape:

```json
{
  "items": [{
    "id": "mem_...",
    "source_type": "browser",
    "source_id": "src_...",
    "title": "SQLite notes",
    "normalized_text": "Saved content...",
    "source_url": "https://docs.example/page",
    "domain": "docs.example",
    "content_hash": "sha256...",
    "captured_at": "2026-10-10T08:00:00Z",
    "request_id": "..."
  }],
  "page": 1,
  "page_size": 12,
  "total": 1,
  "total_pages": 1
}
```

Detail returns `{ "memory": <canonical record>, "source": <source response> }`. Delete returns `{ "deleted": true, "id": "...", "request_id": "..." }`. Missing IDs use `404 NOT_FOUND`; invalid query parameters use `422 VALIDATION_ERROR` with the standard error envelope.

## Frontend and extension

The Timeline calls `GET /memories` for search, date/domain/source filters, and pagination. Aborted requests are ignored when filters change. Detail fetches actual content/source and calls DELETE only after confirmation. Loading, empty, no-results, and retryable error states are distinct; API failures never fall back to mock records. Set `VITE_API_BASE_URL` to override the default `http://127.0.0.1:8000/api/v1`.

The extension still saves captures locally first. Its popup now has an explicit **Send captures to local RecallAI API** opt-in. Enabling it asks Chrome for the one optional origin `http://127.0.0.1:8000/*`; it is off by default, and no required host permission was added. The popup configures `POST /api/v1/ingest/browser`. The permission prompt and real Chrome capture flow still require a manual check.

## Run locally

Terminal 1:

```bash
cd backend
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2:

```bash
npm run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173/timeline`; API docs are at `http://127.0.0.1:8000/docs`. The backend allows only the local Vite origins by default. To point the frontend elsewhere, set `VITE_API_BASE_URL`; to change CORS, set `RECALLAI_CORS_ORIGINS` to an explicit comma-separated allowlist.

## Verification and known limitations

Verified on 2026-10-11:

- Backend: `cd backend && .venv/bin/python -m pytest` — **76 passed**.
- Re-verified later the same day (after Module 5 Task 5.4): full backend suite — **99 passed**; a temporary-database end-to-end run of the whole API surface (ingest, dedupe, search, filters, pagination, detail, source, delete, restart persistence) passed **26/26 checks** against a live uvicorn server.
- Frontend/extension unit tests: `npm test` — **50 passed**.
- `npm run lint`, `npm run build`, `npm run typecheck:extension`, and `npm run build:extension` — all exit 0.
- Fresh Alembic migration, repeat upgrade over a populated database, FTS5 availability, FK enforcement, rollback, corrupt DB handling, and persistence through a newly opened engine are covered by tests.
- Live local smoke test created one browser capture, one transcript, and one note; the Timeline showed all three, search and combined filters narrowed results, detail/source rendered, confirmed deletion removed the browser record from search, and a FastAPI process restart retained the other two.
- The extension package and optional permission manifest build were verified, but actual Chrome permission/capture clicks were not performed.

Known limitations: the React Overview and mock-AI screens remain sample-data experiences; only Timeline and Detail are connected to persisted backend memories. The extension-to-backend step is opt-in and awaits manual Chrome verification. A failed database write is reported safely as `STORAGE_ERROR`; the liveness endpoint does not perform a database readiness probe. ESLint currently warns that installed TypeScript 5.9.3 is newer than the supported range for the installed typescript-eslint parser; the configured lint still exits 0. Existing React Router test warnings and a Starlette multipart deprecation warning remain.
