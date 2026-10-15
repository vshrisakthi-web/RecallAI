# RecallAI — Module 7: MCP Integration

> A Model Context Protocol server that exposes RecallAI's **existing** memory
> capabilities to external MCP-compatible AI clients (Claude, Cline, MCP
> Inspector, …). MCP is a new integration layer only: it reuses the Module 3–6
> services and the same SQLite database. Nothing is rebuilt, and nothing is
> written — every MCP tool is read-only.
>
> Tasks: 61 (understand/inspect) · 62 (server setup) · 63 (`search_memories`)
> · 64 (`get_memory`) · 65 (`search_sources_by_date`) · 66
> (`get_related_memories`) · 67 (validation) · 68 (privacy/errors) · 69
> (external client) · 70 (docs/final verification).

---

## Task 61 — Architecture note: MCP mapped onto existing RecallAI services

### Verified baseline (this session, 2026-10-12)

- Git: `HEAD = 8785317` on `main` (= `origin/main`, Module 2 commit). All
  Module 3–6 work is **local and uncommitted**; nothing staged;
  `git diff --check` clean.
- Backend suite: **344 passed** (`backend/.venv`, Python 3.9.6). Frontend:
  **59 passed**; tsc and lint clean.
- Runtime: the backend venv is Python **3.9.6**. The official MCP Python SDK
  (`mcp` on PyPI) requires Python **≥ 3.10** for every released version, so
  the SDK cannot live in the existing venv. A **second, dedicated venv**
  (`backend/.venv-mcp`, built on the already-installed Homebrew
  Python 3.14) will run the MCP server; the FastAPI venv is untouched.

### Data flow

```
MCP host (Claude / Cline / Inspector)
  └─ MCP client (host built-in)
       └─ stdio  ←→  RecallAI MCP server  (backend/app/mcp_server/server.py)
            └─ app.mcp_server.tools  (thin adapters, validation only)
                 ├─ HybridRetrievalService   (Tasks 6.5/6.6 — semantic+keyword+RRF)
                 ├─ MemoryRepository          (Module 4 — records, list/filter)
                 ├─ ChunkRepository           (Task 6.1 — chunk rows)
                 ├─ VectorStore               (Task 6.3 — stored embeddings)
                 └─ EmbeddingService          (Task 6.2 — loopback-only fallback)
                      └─ SQLite: memories / memory_chunks / chunk_embeddings
```

The MCP server process opens the **same database file** as FastAPI
(`RECALLAI_DB_PATH`, default `backend/data/recallai.db`). Both are local,
single-user, read-only over MCP.

### Tool → existing service mapping

| MCP tool | Reuses (never reimplemented) | Returns |
|---|---|---|
| `search_memories(query, limit)` | `HybridRetrievalService.retrieve()` — one call runs semantic + keyword channels and RRF fusion (`app/services/hybrid.py`) | ranked evidence: memory/chunk ids, excerpt (`passage`), title, source URL/domain/type, `captured_at`, similarity, fused score, matched channels |
| `get_memory(memory_id)` | `MemoryRepository.get_by_id()` (`app/repositories/sqlite_store.py`) + `is_safe_id()` (`app/services/hashing.py`) | one record: id, title, full text, source url/domain/type, captured/ingested timestamps, tags |
| `search_sources_by_date(start_date, end_date, source_type?, limit?)` | `MemoryRepository.list_memories(from_date=…, to_date=…, source_type=…, page_size=…)` — the exact filter the `GET /api/v1/memories` route uses | memory summaries (id, title, url, domain, type, `captured_at`) |
| `get_related_memories(memory_id, limit)` | `ChunkRepository.get_chunks()` + `VectorStore.get()`/`search()` (stored embedding first; `EmbeddingService.embed_query()` only as fallback) | related memories with similarity scores; original excluded |

### MCP tools vs. ordinary REST endpoints

- **Discovery and self-description.** An MCP host calls `tools/list` and
  receives each tool's JSON schema (names, types, bounds, descriptions) —
  the client can offer the tools to its model without hard-coded knowledge.
  REST needs OpenAPI plus a human/agent to interpret it.
- **Invocation semantics.** A tool call is one framed JSON-RPC request over
  the transport (stdio here) with structured success/error results
  (`isError`), designed for an LLM to call mid-conversation. REST is
  request/response HTTP aimed at applications, with status codes and
  envelopes instead.
- **Session model.** MCP servers are launched *by* the host as local
  subprocesses (or connected over Streamable HTTP); no ports, no CORS, no
  public binding. That fits RecallAI's privacy posture better than adding
  another listening socket.
- **Same underlying logic either way.** `search_memories` deliberately
  mirrors `POST /api/v1/ask`: identical service, identical evidence, no
  second search implementation.

### Missing capabilities / gaps found during inspection

1. **No MCP code existed** — the server, tools, tests, and docs are all new
   (Tasks 62–70).
2. **Python floor.** The MCP SDK needs ≥ 3.10; the backend venv is 3.9.
   Solved by the dedicated `backend/.venv-mcp` (Python 3.14). FastAPI and
   its pinned deps stay exactly as they are.
3. **`get_related_memories` has no direct service** — the Module 6 retrieval
   searches by *question text*, not by "more like this record". The tool
   composes existing primitives (chunk rows → stored vector →
   `VectorStore.search`) without adding a new index or embedding system.
4. **Read-only surface.** No ingestion, deletion, summarization, or
   settings tools are exposed; the memory-collection boundary is the whole
   database and nothing else (no SQL, no filesystem tools).

Task 61 status: **PASS** — design grounded in the file paths and function
names above; no duplicate database or search implementation proposed; all
Module 1–6 work preserved untouched.
