# RecallAI — Project Context

> **Purpose:** A concise, source-of-truth summary so future coding sessions can
> resume without losing context.
> **Source of truth:** `README.md` and `docs/mvp-requirements.md`.
> Details that cannot be verified from those files are marked **[UNKNOWN]**.

- **Repository location:** `/Users/shrisakthi/projects/RecallAI`
- **Remote:** `https://github.com/vshrisakthi-web/RecallAI.git` (branch: `main`)
- **Latest commit:** `8785317` — Module 2 extension, still `origin/main`.
- **Last updated:** 2026-10-11 after Module 5 completion (Tasks 5.7–5.10). Modules 3–5
  changes and documentation are local uncommitted work; inspect `git status` before
  editing, staging, or committing. Module 4 verification and Module 5 progress are
  recorded in `docs/PROGRESS.md`.

---

## Product Vision

RecallAI is a **privacy-first personal AI memory assistant**. It helps users
capture, organize, and recall information they encounter across the web — without
sending personal data to third parties. Guiding principle: **"your memory stays
yours."** It should feel like a trusted second brain: lightweight, fast, and
privacy-respecting.

## Target Users

- **Primary:** the privacy-conscious knowledge worker / student — saves articles,
  notes, links, and snippets across many tools and wants one place to recall them
  later, but is uncomfortable with cloud services that transmit personal data.
- **Secondary (future, out of MVP scope):** researchers with large personal
  corpora; teams (deferred — requires shared/remote storage).

## MVP Scope

The MVP proves the core value loop with minimal scope:

1. **Capture** — save a memory item (text, link, or note) quickly from the browser.
2. **Store locally** — persist items on the user's device; no data leaves by default.
3. **Recall / browse** — view, search, and revisit saved memories.
4. **Demonstrate privacy-first design** — works end-to-end on local data with
   mock/offline AI behavior; no personal data transmitted externally.

**Non-goals:** full natural-language AI, cross-device sync, collaboration, and any
remote/cloud server infrastructure. The current FastAPI service is local-only.

## Planned Interfaces

Three user-facing surfaces were specified. **Detailed specification (Task 1.2, done):**
see `docs/interface-specification.md` (purpose, actions, content, states,
navigation, and an ownership matrix per surface).

- **Chrome Extension Popup** — quick capture control + at-a-glance recall from the
  toolbar; owns capture state (`active`/`paused`/`stopped`) and current-page capture.
- **Companion Side Panel** — persistent contextual Q&A about the current page, with
  source references and related memories.
- **Web Dashboard** — full-screen management with five screens: **Overview, Memory
  Timeline, Ask RecallAI, Memory Detail, Privacy Settings**; owns browsing, editing,
  deletion, and all settings.

## Current Technology Decisions

Decided (from `docs/mvp-requirements.md`, Section 7) **and now implemented** (Task 1.9):

- **Frontend stack:** **React 18 + TypeScript (strict)**.
- **Build tool:** **Vite 5** (`npm run dev` / `npm run build` / `npm run preview`).
- **Styling:** **Tailwind CSS 3** (`tailwind.config.js`, `postcss.config.js`,
  `src/index.css`). Custom palette in the config (canvas/surface/brand/safe/warn).
- **Routing:** **React Router 6** (`src/App.tsx`). Dashboard routes share `AppLayout`;
  `/popup` and `/panel` are isolated extension-preview routes.
- **Mock/demo data:** typed sample data remains in `src/data/` for Overview and
  mock-AI/demo screens. The production Memory Timeline and Detail use the real API.
- **State management:** React Context (`src/state/MemoriesContext.tsx`) — no external
  state library (kept intentionally simple for the MVP).
- **Testing:** **Vitest 2 + React Testing Library** (`npm test`); ESLint 8
  (`npm run lint`, `--max-warnings 0`).
- **Extension target (IMPLEMENTED in Module 2):** a **Manifest V3 Chrome extension**
  under `extension/` — React popup + IIFE content script + MV3 service worker.
  Built via `npm run build:extension` → `extension/dist-extension/` (Load unpacked).
  Required permissions: `activeTab` + `scripting` + `storage` (no required
  `host_permissions`). An explicit popup opt-in requests only optional access to
  `http://127.0.0.1:8000/*`. The
  dashboard's `/popup` and `/panel` remain isolated preview routes.
- **Extension persistence (IMPLEMENTED):** `chrome.storage.local` via
  `extension/lib/storage.ts` (`CaptureRepository`) for records + capture state.
- **Extension backend adapter:** remains local-first; optional localhost API sync is
  disabled by default and requires explicit user permission.
- **Backend persistence (Module 4):** FastAPI ingestion now stores in SQLAlchemy / SQLite
  at `backend/data/recallai.db`; Timeline and Detail call the API. The JSON store is
  retained only for legacy import and regression tests.
- **Local summarization (Module 5 — complete, Tasks 5.2–5.10):** `POST
  /api/v1/memories/{memory_id}/summary` summarizes a memory's stored text with a
  **local Ollama model over loopback only** (default `http://127.0.0.1:11434`;
  this machine runs model `llama3.2:1b` pinned via `backend/.env`); a
  non-loopback base URL is rejected before any request and no credentials exist
  on this path, so memory text never leaves the device. The Memory Detail screen
  exposes a user-initiated **“Generate AI Summary”** button (loading, error,
  regenerate, and stale-response handling) via `summarizeMemory()` in
  `src/lib/memoriesApi.ts`. **Live-verified 2026-10-11:** real Ollama 0.40.3 +
  `llama3.2:1b` produced a real summary through FastAPI in ~3 s; full backend
  (132) and frontend (54) suites pass. A fully offline run and a manual UI
  click-through remain unverified (documented in
  `docs/module-5-local-ai-summarization.md`). The earlier hosted Gemini settings
  and `GeminiSummarizationService` remain in the codebase with their tests but no
  runtime route imports them. Configuration is backend-only and never sent to
  React or the extension.
- **AI (planned):** simulated with **mock responses** (visible "Mock answer" badges);
  no external AI services in the MVP.
- **TypeScript throughout:** type safety enforced (strict `tsconfig`).

## Development Workflow

Observed from how the project is being run:

- Work proceeds **one task at a time**, organized as **Modules → Tasks**
  (e.g., "Module 1, Task 1.1").
- **Documentation-first:** requirements/context are written before code.
- **Standard commands:** `npm run dev` (local dev server), `npm run build` (tsc + Vite),
  `npm run preview` (serve the build), `npm test` (Vitest), `npm run lint` (ESLint).
- Mock/demo surfaces remain independently usable; the Timeline/Detail require the
  local backend and show an error instead of silently using sample memories.
- The user authorized **autonomous completion of Module 1** (no per-task approval gates),
  with each task inspected/implemented/tested/documented/verified before being marked
  complete, and verified work committed + pushed to `origin/main`.

## Important Constraints / Guardrails

- **Privacy-first:** all personal memory data stays local; transmit nothing
  off-device by default; extension-to-backend sync is explicit, optional, and
  restricted to loopback; use mock/offline AI; no third-party analytics/trackers; be
  transparent to the user.
- **Mock AI is always labelled:** Ask RecallAI and the side panel render every answer
  with a visible "Mock answer" badge; no fake live-AI backend.
- **Out of scope for MVP** (see `mvp-requirements.md` §8): real AI/LLM calls, cloud
  sync, accounts/auth, teams, mobile apps, non-Chrome browsers, data import/export,
  offline AI models, monetization, analytics.

## Unknowns / Not Yet Decided

The following are **not decided or not present** and must not be assumed:

- **Task 1.8 Stitch designs** — Memory Detail + Privacy Settings exports are **missing**
  (prompts 8a/8b ready in `docs/stitch-prompts.md`; user must generate them).
- **Designs 1.4–1.7** are generated but **not yet approved** (awaiting user review).
- **Extension packaging/build pipeline** — ✅ **IMPLEMENTED in Module 2** (`npm run
  build:extension`). **Manual Chrome verification is pending** (Load unpacked +
  checklist). Packaging the companion as a real `chrome.sidePanel` remains future work.
- **Direct Dashboard ↔ extension storage bridge** — none. Timeline and Detail use
  FastAPI/SQLite; extension records remain in `chrome.storage.local` unless the user
  explicitly enables its localhost API adapter. Real Chrome permission/capture
  verification is still pending.
- **Module 4 backend/UI** — implemented locally and automatically tested; see the
  module guide for current test results and outstanding manual Chrome verification.
- **CI pipeline** — none configured.
