# RecallAI — Project Context

> **Purpose:** A concise, source-of-truth summary so future coding sessions can
> resume without losing context.
> **Source of truth:** `README.md` and `docs/mvp-requirements.md`.
> Details that cannot be verified from those files are marked **[UNKNOWN]**.

- **Repository location:** `/Users/shrisakthi/projects/RecallAI`
- **Remote:** `https://github.com/vshrisakthi-web/RecallAI.git` (branch: `main`)
- **Latest commit:** see `git log` — **Module 2 (Chrome extension) committed & pushed
  on top of Module 1.** (Module 1's last commit was `48176d2`; Overview export
  `c2efb16`.)
- **Last updated:** during **Module 2 — Tasks 2.1–2.10 (Chrome extension & capture
  engine).** A Manifest V3 extension under `extension/` builds a loadable
  `extension/dist-extension/` (`npm run build:extension`); build, extension
  typecheck, lint, and **44 tests** (13 Module 1 + 31 Module 2) pass. **Manual Chrome
  verification is the only outstanding step.** Guide: `docs/module-2-chrome-extension.md`.

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
server-side infrastructure.

## Planned Interfaces

Three user-facing surfaces are planned. **Detailed specification (Task 1.2, done):**
see `docs/interface-specification.md` (purpose, actions, content, states,
navigation, and an ownership matrix per surface). None are built yet.

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
- **Initial data:** **typed mock data** in `src/data/` (separate from components) in
  place of a real backend.
- **State management:** React Context (`src/state/MemoriesContext.tsx`) — no external
  state library (kept intentionally simple for the MVP).
- **Testing:** **Vitest 2 + React Testing Library** (`npm test`); ESLint 8
  (`npm run lint`, `--max-warnings 0`).
- **Extension target (IMPLEMENTED in Module 2):** a **Manifest V3 Chrome extension**
  under `extension/` — React popup + IIFE content script + MV3 service worker.
  Built via `npm run build:extension` → `extension/dist-extension/` (Load unpacked).
  Permissions: `activeTab` + `scripting` + `storage` (no `host_permissions`). The
  dashboard's `/popup` and `/panel` remain isolated preview routes.
- **Extension persistence (IMPLEMENTED):** `chrome.storage.local` via
  `extension/lib/storage.ts` (`CaptureRepository`) for records + capture state.
  The dashboard still uses mock data (no bridge between the two stores yet —
  Module 3 candidate).
- **Local persistence (dashboard, planned):** the dashboard's mock data is not yet
  backed by IndexedDB/localStorage; no shared bridge to extension storage yet.
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
- The frontend is built against **mock data** so the UI can be built and demonstrated
  independently of a backend.
- The user authorized **autonomous completion of Module 1** (no per-task approval gates),
  with each task inspected/implemented/tested/documented/verified before being marked
  complete, and verified work committed + pushed to `origin/main`.

## Important Constraints / Guardrails

- **Privacy-first:** all personal memory data stays local; transmit nothing
  off-device; use mock/offline AI; no third-party analytics/trackers; be
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
  checklist). Packaging the companion as a real `chrome.sidePanel` is still a
  Module 3 candidate.
- **Dashboard ↔ extension storage bridge** — none yet (dashboard = mock data,
  extension = `chrome.storage.local`); a Module 3 candidate, not built.
- **CI pipeline** — none configured.
