# Module 3 — Backend Ingestion Pipeline

> Local FastAPI service that ingests **browser captures**, **transcript imports**,
> and **manual notes**; validates, normalizes, deduplicates, and persists them.
> Privacy-first: it never fetches URLs, never calls external AI, and stores
> everything on the local machine. Intended for **local development only** —
> secure it before any network exposure.

> **Module 4 update:** the active API now persists to SQLite. This guide preserves
> the Module 3 JSON-store contract and historical tests; `JsonFileRepository` remains
> only for legacy import/regression coverage. See
> [`module-4-structured-memory.md`](module-4-structured-memory.md) for current storage.

---

## 1. Quick start

```bash
cd backend
python3 -m venv .venv                 # already created in this repo
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
```

- **Swagger UI:** <http://127.0.0.1:8000/docs>
- **Health check:** `GET http://127.0.0.1:8000/api/v1/health`
- **Base path:** all routes live under `/api/v1`.

Run the test suite:

```bash
cd backend && .venv/bin/python -m pytest
```

---

## 2. Endpoints

| Method | Path                      | Purpose                                  | Success codes |
|--------|---------------------------|------------------------------------------|---------------|
| GET    | `/api/v1/health`          | Liveness + version                        | `200`         |
| POST   | `/api/v1/ingest/browser`  | Ingest a browser capture (`CaptureRecord`)| `201` created, `200` duplicate |
| POST   | `/api/v1/ingest/transcript` | Ingest imported transcript text         | `201` created, `200` duplicate |
| POST   | `/api/v1/ingest/notes`    | Ingest a manual note                      | `201` created, `200` duplicate |
| GET    | `/docs`, `/openapi.json`  | Interactive docs / schema                 | `200`         |

Every response carries an **`X-Request-ID`** header, and every stored record
echoes the same id in `record.request_id`. A client may supply its own
`X-Request-ID` (≤128 chars, `[A-Za-z0-9._:-]`); unsafe values are rejected with
`400 INVALID_REQUEST_ID`.

---

## 3. Request schemas

### 3.1 Browser capture — `POST /api/v1/ingest/browser`

Field names intentionally **mirror the extension's camelCase `CaptureRecord`**
(`extension/types/index.ts`) so `extension/lib/backend.ts` can POST a record
directly with no translation layer.

| Field              | Type    | Required | Notes |
|--------------------|---------|----------|-------|
| `id`               | string  | no       | Extension id. If absent/unsafe the server mints one. |
| `title`            | string  | yes      | Non-empty, ≤300 chars. |
| `url`              | string  | yes      | `http`/`https` only, ≤2048 chars. |
| `domain`           | string  | yes      | Must match the URL host. |
| `capturedAt`       | string  | yes      | ISO 8601 **timezone-aware**; naive timestamps rejected. |
| `captureType`      | enum    | yes      | `full-page` \| `selection`. |
| `extractedText`    | string  | yes      | Non-empty, ≤200,000 chars. |
| `selectedText`     | string  | cond.    | Required (non-empty) when `captureType = selection`; ≤50,000. |
| `surroundingContext`| string | no       | ≤50,000. |
| `status`           | enum    | no       | `ok` \| `empty` \| `partial` \| `unsupported` \| `error` (default `ok`). |
| `contentLength`    | int     | no       | Accepted for compat; **recomputed server-side** (not trusted). |
| `note`             | string  | no       | e.g. why a field was unavailable. |

`extra = forbid` — unknown fields (e.g. a stray `capturedAt` on the wrong
endpoint) return `422`.

**Example — created (`201`):**

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/ingest/browser \
  -H 'Content-Type: application/json' -H 'X-Request-ID: smoke-br-1' \
  -d '{
    "id": "mem_smoke", "title": "Vector DB Notes",
    "url": "https://techblog.example/vector-db", "domain": "techblog.example",
    "capturedAt": "2026-10-11T08:00:00Z", "captureType": "full-page",
    "extractedText": "Vector databases  store embeddings.",
    "status": "ok", "contentLength": 31
  }'
```

```json
{
  "duplicate": false,
  "status": "created",
  "message": "Record accepted and stored.",
  "record_id": "mem_smoke",
  "source_type": "browser",
  "content_hash": "d391abfb7a2be427340d1d9213f8204eeb269f537eaf4b33337d1352a52a0c69",
  "record": {
    "id": "mem_smoke",
    "source_type": "browser",
    "title": "Vector DB Notes",
    "normalized_text": "Vector databases store embeddings.",
    "source_url": "https://techblog.example/vector-db",
    "domain": "techblog.example",
    "source_metadata": {},
    "captured_at": "2026-10-11T08:00:00Z",
    "ingested_at": "2026-10-11T08:48:30.799872Z",
    "content_hash": "d391abfb7a2be427340d1d9213f8204eeb269f537eaf4b33337d1352a52a0c69",
    "request_id": "smoke-br-1",
    "capture_type": "full-page",
    "selected_text": null,
    "surrounding_context": null,
    "extraction_status": "ok",
    "note": null
  }
}
```

Re-posting the identical body returns **`200`** with `"duplicate": true` and the
same `record_id`.
### 3.2 Transcript — `POST /api/v1/ingest/transcript`

| Field         | Type   | Required | Notes |
|---------------|--------|----------|-------|
| `title`       | string | yes      | Non-empty, ≤300. |
| `transcript`  | string | yes      | Non-empty, ≤500,000. |
| `source_url`  | string | no       | `http`/`https`; `domain` derived from it. |
| `source`      | string | no       | Where it came from (e.g. `podcast.example`). |
| `metadata`    | object | no       | ≤50 keys, scalar values, depth ≤2, value ≤1000 chars. |
| `captured_at` | string | no       | **snake_case**; timezone-aware. Defaults to ingestion time. |

The backend **does not fetch** transcript content — it only processes text you
submit.

**Example — created (`201`):**

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/ingest/transcript \
  -H 'Content-Type: application/json' \
  -d '{"title":"Podcast Ep12","source_url":"https://podcast.example/ep12",
       "source":"podcast.example","transcript":"Welcome   to the show.",
       "captured_at":"2026-10-11T09:00:00+00:00",
       "metadata":{"duration_seconds":1820}}'
```

→ `normalized_text`: `"Welcome to the show."` (whitespace collapsed),
`record_id`: `tr_893354660abdc75a6694b94a`. Identical body → `200` duplicate.

### 3.3 Manual note — `POST /api/v1/ingest/notes`

| Field         | Type     | Required | Notes |
|---------------|----------|----------|-------|
| `title`       | string   | yes      | Non-empty, ≤300. |
| `note`        | string   | yes      | Non-empty, ≤50,000. |
| `source_url`  | string   | no       | Optional reference link; `domain` derived. |
| `tags`        | string[] | no       | ≤50 tags, each ≤1000 chars, non-empty. |
| `metadata`    | object   | no       | Same bounds as transcript metadata. |
| `captured_at` | string   | no       | **snake_case**; timezone-aware. |

**Example — created (`201`):**

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/ingest/notes \
  -H 'Content-Type: application/json' \
  -d '{"title":"HNSW idea","note":"Read the HNSW  paper.",
       "captured_at":"2026-10-11T09:05:00Z","tags":["reading"],
       "metadata":{"source":"manual"}}'
```

→ `normalized_text`: `"Read the HNSW paper."`, `record_id`: `note_7cf5899a40f646ca2d59861f`.

---

## 4. Error envelope

All errors share one shape; there are **no stack traces or internals** in
responses (they are logged server-side only):

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "The submitted request is invalid.",
    "details": [
      { "field": "url", "issue": "Value error, url must use the http or https scheme", "type": "value_error" }
    ],
    "request_id": "350a6a96a0571c05"
  }
}
```

| HTTP | `code`              | When |
|------|---------------------|------|
| 400  | `INVALID_REQUEST_ID`| Client sent an unsafe `X-Request-ID`. |
| 422  | `VALIDATION_ERROR`  | Schema/field/size/URL/timestamp/metadata failure (incl. malformed JSON). |
| 500  | `STORAGE_ERROR`     | Persistence failed (disk/IO). |
| 500  | `INTERNAL_ERROR`    | Any unhandled exception. |
| 404  | `NOT_FOUND`         | Unknown route. |

A failed request **persists nothing** — validation happens before any write, so
there are no partial records.

---

## 5. Normalization & deduplication

**Normalization** (`app/services/normalize.py`) is deterministic:

1. Line endings → `\n` (CRLF/CR normalized).
2. Leading indentation preserved (code blocks survive).
3. Internal runs of spaces/tabs → one space; trailing whitespace stripped per line.
4. Runs of 2+ blank lines → a single blank line (paragraph boundaries kept).
5. Whole-text trim.

**Content hash:** SHA-256 of the normalized text (`app/services/hashing.py`).

**Dedup key** (`app/repositories/json_store.py`):

```
source_type + source_url + capture_type + content_hash
```

- The **title is excluded** so two distinct notes that share a title are **not**
  merged; distinct notes have different `content_hash`.
- Same URL + same content → **duplicate** (idempotent retries, returns existing id).
- Same URL + **changed** content → **new record** (history is kept).
- `selection` vs `full-page` are distinct captures.

The repository is idempotent for retries. Its thread-lock guarantees atomicity
**within one process only** — it is **not multi-process safe** (documented
limitation).

---

## 6. Storage

- Backend: `JsonFileRepository` implementing the abstract `IngestionRepository`
  (`app/repositories/base.py`), so the store is swappable (e.g. SQLite later).
- File: `backend/data/ingested.json` (override with `RECALLAI_STORAGE_PATH`).
- Writes are atomic (temp-file → rename) with a thread lock; the file persists
  across restarts. **`backend/data/` is git-ignored — never committed.**

## 7. Configuration (`RECALLAI_*` env vars)

| Var | Default | Meaning |
|-----|---------|---------|
| `RECALLAI_STORAGE_PATH` | `backend/data/ingested.json` | Storage file. |
| `RECALLAI_MAX_BROWSER_TEXT` | `200000` | Max `extractedText` chars. |
| `RECALLAI_MAX_TRANSCRIPT_TEXT` | `500000` | Max transcript chars. |
| `RECALLAI_MAX_NOTE_TEXT` | `50000` | Max note chars. |
| `RECALLAI_MAX_SELECTION_TEXT` / `..._CONTEXT_TEXT` | `50000` | Selection/context caps. |
| `RECALLAI_MAX_TITLE` | `300` | Title cap. |
| `RECALLAI_MAX_URL` | `2048` | URL cap. |
| `RECALLAI_MAX_METADATA_ITEMS` / `_VALUE` / `_DEPTH` | `50 / 1000 / 2` | Metadata bounds. |
| `RECALLAI_MAX_REQUEST_ID` | `128` | `X-Request-ID` cap. |
| `RECALLAI_MAX_FUTURE_SKEW_MINUTES` | `1440` | Reject timestamps too far ahead. |
| `RECALLAI_MIN_YEAR` | `2000` | Earliest accepted year. |
| `RECALLAI_CORS_ORIGINS` | *(empty)* | Off unless set (comma-separated). |

---

## 8. Architecture

```
app/
├── main.py                 # create_app(): middleware, routers, exception handlers
├── core/                   # config, errors (envelope), request_id, validation
├── middleware/request_id.py # assigns/echoes X-Request-ID
├── schemas/                # common (CanonicalRecord/enums), browser, transcript, note
├── services/               # normalize, hashing, ingestion (orchestration)
├── repositories/           # base (IngestionRepository, StorageError), json_store
└── api/                    # deps (DI), routes/health, routes/ingestion
```

Request flow: **route → Pydantic schema (validate) → ingestion service
(normalize → hash → dedup via repository) → `IngestionResult`**.

## 9. Extension integration

`BrowserCaptureIn` accepts exactly the 12 fields of the extension's
`CaptureRecord` (`id, title, url, domain, capturedAt, captureType, extractedText,
selectedText?, surroundingContext?, status, contentLength, note?`) — **no adapter
change was required.** To enable, point `extension/lib/backend.ts`'s
`BackendConfig.endpoint` at a full URL such as
`http://localhost:8000/api/v1/ingest/browser`. The adapter stays **disabled by
default**, is localhost-only, and is never called automatically.

> Edge case: an extension capture whose `status` is `empty`/`error` with empty
> `extractedText` would be rejected (empty text is invalid) — by design the
> backend only stores real content.

## 10. Tests

`backend/tests/` — **59 passing** (`pytest`):

- `test_normalize.py` — line endings, whitespace collapse, blank-line collapse,
  determinism, indentation preservation, hash/id helpers.
- `test_repository.py` — dedup key behavior, persistence across restarts, id
  collisions, recent-list ordering, title-independence.
- `test_browser.py`, `test_transcript.py`, `test_notes.py` — happy paths + each
  validation rule (URL/scheme/domain, timestamps, sizes, empty, duplicates,
  changed content, metadata bounds).
- `test_health_errors.py` — health, request-id header/body, malformed JSON,
  missing fields, structured error envelope.
- `test_storage_errors.py` — simulated storage failure → safe 500, no partial
  records, real on-disk persistence.

All Module 1 + Module 2 checks still pass: `npm test` (44), `npm run lint`,
`npm run build`, `npm run typecheck:extension`, `npm run build:extension`.

