# Module 8 — Agent Harness Design (Tasks 71–80)

This document is the design of record for the RecallAI agent harness. It is
referenced by the docstrings in `backend/app/agents/` and describes the state
model, stage contracts, policies/limits, and control flow **as implemented**.
It is intentionally prose-and-decisions, not a second copy of the code: the
code and its tests are the executable specification; this file explains *why*
the boundaries are drawn where they are.

## Objective and core principle

Module 8 turns memory search + Q&A into a **controlled, evidence-grounded
workflow**: understand an objective, retrieve evidence, analyze it while
distinguishing facts/inferences/unknowns, draft actionable tasks, validate
every stage, and persist a task **only after an explicit, valid user
approval**.

It is **not** a chat swarm and **not** an orchestration framework. It is a
plain-Python pipeline with typed shared state, explicit stage contracts,
capabilities, bounded limits, timeouts, bounded retries, sanitized traces, and
human approval. A single local model (Ollama) serves the analysis and task
roles with different instructions and schemas. No new framework (LangGraph,
etc.) was introduced, and no second database or parallel memory stack exists.

## Reuse map (verified)

- **Retrieval:** `app.services.hybrid.HybridRetrievalService.retrieve(question, top_k=..., from_date=..., to_date=...) -> RetrievalResult` (Module 6, keyword + semantic with RRF fusion). Evidence objects come from `app.services.evidence.Evidence` (`chunk_id`, `memory_id`, `passage`, `source_*`, `similarity`, `score`).
- **Local LLM:** loopback-only Ollama chat, mirroring `app.services.summarization.OllamaSummarizationService` conventions (`ollama_base_url`, `ollama_model`, `ollama_timeout_seconds`; no credentials; low temperature; bounded `num_predict`).
- **IDs:** `app.services.hashing.new_id(prefix)` and `is_safe_id` for `run_id` (server-generated, unguessable, URL-safe).
- **Config/env:** `app.core.config.Settings` exposes `RECALLAI_AGENT_*` overrides (see `policies.py`).

## Workflow state (`app/agents/state.py`)

One run = one `WorkflowState`. Stages never talk to each other; they read and
write only this shared, typed record.

- **`run_id`**: `run_<id>`, unique per run, safe in URLs.
- **`user_query`**, **`objective`**, **`status`**, **`errors`**, and the stage
  outputs **`evidence`**, **`analysis`**, **`task_drafts`**, plus **`trace`**
  and **`clarification`**.
- **`status`** is a closed enum: `PENDING`, `RUNNING`, `AWAITING_APPROVAL`,
  `COMPLETED`, `FAILED`, `REJECTED`, `CANCELLED`. Transitions are validated
  against a fixed map; any illegal move raises `InvalidTransitionError`, so a
  failure can never silently become a success (and terminal states are final).
- **`objective`** is a closed enum: `SEARCH`, `SUMMARIZE`, `ANALYZE_LEARNING`,
  `CREATE_TASKS`. `set_objective` accepts only these (or their string values);
  arbitrary model output is rejected.
- **Errors and traces keep only safe fields** (stage, category, bounded
  message, duration, attempts) — never raw prompts, memory text, secrets, or
  full exception detail.

State is **transient while a run executes**. Persisting runs and approved
tasks is a separate, approval-gated concern (Task 79).

## Stage contracts and capabilities (`app/agents/contracts.py`)

Each stage has a written contract as *data* (testable, not comments):

| Stage | requires (present, not None) | produces (only these fields) | capabilities | persists |
|---|---|---|---|---|
| router | `user_query` | `objective`, `clarification`, `confidence` | `read_query` | no |
| retrieval | `user_query`, `objective` | `evidence` | `read_query`, `search_memories` | no |
| analysis | `objective`, `evidence` | `analysis` | `call_local_llm` | no |
| task | `objective`, `analysis`, `evidence` | `task_drafts` | `call_local_llm`, `draft_tasks` | no |
| approval | `run_id`, `decision`, `task_drafts` | `decision`, `persisted_task_ids` | `persist_approved_tasks` | **yes** |

An empty evidence list counts as *present* (no matches is a valid result, not a
missing input). `validate_stage_output` rejects any field outside a stage's
`produces` allowlist, so model output cannot smuggle in arbitrary actions.
`require_capability` gates each external effect; only the approval stage may
perform a durable write.

Evidence rules enforced by contracts and agents:

- **MISSING_EVIDENCE_RULE** — absence of a record is not proof of absence; say
  "the records do not show this", never "it was not done".
- **CONFLICTING_EVIDENCE_RULE** — report conflicts citing both sides; never
  silently pick a winner.
- **UNSUPPORTED_CLAIM_RULE** — substantive findings must cite retrieved
  evidence; unsupported claims are labelled inference/unknown.
- **APPROVAL_RULE** — only a real application decision persists tasks; an
  LLM statement (including "the user approved") is never approval.
- **PERSISTENCE_RULE** — of the defined stages, only `approval` writes durable
  task records.

## Policies and limits (`app/agents/policies.py`)

`HarnessPolicy` is a frozen value object, every field env-overridable
(`RECALLAI_AGENT_*`), validated so `total_budget_seconds >= stage_timeout_seconds`
and every bound is at least 1:

- `max_query_chars`, `max_evidence_items`, `max_evidence_chars` (evidence
  budget), `max_tasks`, `max_task_title_chars`, `max_task_description_chars`.
- `stage_timeout_seconds` (per-stage wall-clock), `total_budget_seconds`
  (whole-run wall-clock), `max_attempts` (per stage), `max_errors` (bounded
  user-facing error list, oldest dropped).

## Control flow (`app/agents/orchestrator.py`)

1. Create a unique `run_id`; validate the question (empty/oversized →
   `WorkflowRequestError` → HTTP 422). Start `PENDING` → `RUNNING`.
2. **Router.** A clarification stops the run before retrieval (no objective →
   no later stage acts on an unclear request). A router failure fails the run.
3. **Retrieval** (every objective that reached here).
4. **Analysis** for `SUMMARIZE` / `ANALYZE_LEARNING` / `CREATE_TASKS`.
5. **Task drafting** only for `CREATE_TASKS`.
6. Each stage runs under a per-stage timeout (`stage_timeout_seconds`) and the
   run-level budget guard (`total_budget_seconds`); the first failure marks the
   run `FAILED` and stops it, preserving earlier traces.
7. A successful `CREATE_TASKS` run with drafts rests in `AWAITING_APPROVAL`;
   everything else rests in `COMPLETED`.
8. `build_response` produces a JSON-serializable dict matching the strict
   `WorkflowResponse` schema (enums as `.value` strings; no raw model text).

## Resilience: timeouts, retries, traces, recovery (`app/agents/resilience.py`)

- `call_with_retries(operation, policy=..., is_transient=..., sleeper=...)`
  retries **only transient** failures, bounded by `policy.max_attempts`. It
  never raises: it returns a `RetryResult` carrying `value` on success or the
  final `error` plus the **true attempt count**, so stage traces report real
  retries. Permanent errors (bad input, schema violations, fabricated refs,
  contract/permission errors) return on the first attempt — never retried.
- `run_with_timeout(operation, timeout_seconds=...)` bounds a synchronous,
  blocking local call on a worker thread; a non-positive budget runs inline
  (the transport `timeout=` remains the guard). On overrun it raises
  `StageTimeoutError`, which the orchestrator maps to a safe `FAILED` +
  `timeout` category — never a false success.
- The analysis and task agents route their model calls through
  `call_with_retries`; the retrieval agent routes its service call through it;
  the orchestrator wraps every stage in `run_with_timeout`.
- **No unsafe retries:** retries wrap only idempotent reads/LLM calls.
  Persistence (Task 79) is never retried as a "transient" op.

## Schemas and validation (`app/agents/schemas.py`)

Every model is strict (`extra="forbid"`). `RoutingResult` enforces
exactly-one-of objective/clarification. `WorkflowResponse` enforces
cross-field consistency: clarification runs carry no objective/evidence/
findings/drafts; every finding ref and draft `source_id` must name a retrieved
`chunk_id`; drafts stay `status="draft"`. Invalid stage output is rejected or
handled through a bounded recovery path — never trusted silently.

## Approval boundary (Task 79)

Proposed tasks reach `AWAITING_APPROVAL`. The frontend returns drafts and their
source references. Persistence happens **only** through a distinct, server-side
approval action that re-validates edited drafts and source refs against the
stored run, rejects duplicate/stale/replayed submissions, records the decision
in the trace, and never treats an LLM "approval" as real. Until approval,
drafts exist solely as workflow state and never enter persistent task storage.

## Out of scope / non-goals

- No orchestration framework, no background queues, no distributed state.
- No second database or parallel memory implementation.
- No LLM-invoked tools, SQL, shell, or filesystem actions.
- No changes to Modules 1–7 behaviour.


## Verification (Task 80)

- **End-to-end lifecycle** (`backend/tests/test_e2e_workflow.py`, 14 tests):
  drives the real FastAPI app — `POST /api/v1/workflow` (real router + real
  `HybridRetrievalService` over seeded SQLite with a fake embedding transport,
  fake Ollama for analysis/task) → `awaiting_approval` with drafts (no
  `tasks` rows) → `POST /api/v1/workflow/{run_id}/approve` → persisted +
  `completed`. Also covers reject (nothing persisted), duplicate/replay (404),
  unknown/stale run (404), fabricated source ids on edit (422), valid edit,
  no-relevant-memories, conflicting records, malformed model output, unknown
  source ids in task output, model unavailable, genuine retrieval failure
  (both channels down), and a Task 78 retry exercised end to end (transient
  analysis outage → run still completes; analysis trace shows `attempts >= 2`).
- **Approval boundary** (`backend/tests/test_approval.py`, 22 tests) and
  **resilience** (`backend/tests/test_resilience.py`, 17 tests).
- **Commands:** `cd backend && .venv-mcp/bin/python3.14 -m pytest -p no:warnings
  -q` → 535 passed, 0 failed. Frontend: `npm test` (64 passed), `npx tsc -b
  --noEmit`, `npm run lint`.
- **Frontend approval UI:** `src/pages/WorkflowReview.tsx` renders drafts +
  evidence and provides explicit Approve/Reject actions (route `/workflow`).
- Tests are deterministic and offline; no live LLM/network. A live smoke run
  against a real Ollama model is a manual step, not an automated test.

