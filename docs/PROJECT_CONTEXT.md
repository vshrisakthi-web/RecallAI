# RecallAI — Project Context

> **Purpose:** A concise, source-of-truth summary so future coding sessions can
> resume without losing context.
> **Source of truth:** `README.md` and `docs/mvp-requirements.md`.
> Details that cannot be verified from those files are marked **[UNKNOWN]**.

- **Repository location:** `/Users/shrisakthi/projects/RecallAI`
- **Remote:** `https://github.com/vshrisakthi-web/RecallAI.git` (branch: `main`)
- **Latest commit:** `c2efb16` — "docs: add Overview dashboard design export"
- **Last updated:** during Module 1 — Overview design **approved**; Stitch designs
  1.4–1.7 **generated & organized** into `docs/designs/<screen>/` (pending review);
  Task 1.8 designs **missing** (user must generate). Frontend implementation
  (Task 1.9) is **in progress**.

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

Decided (from `docs/mvp-requirements.md`, Section 7):

- **Frontend stack:** **React + TypeScript**.
- **Initial data:** **mock data** in place of a real backend.
- **Extension target (planned):** Manifest V3 Chrome extension for popup + side
  panel; web dashboard as a standalone page.
- **Local persistence (planned):** browser storage — IndexedDB or `localStorage`.
- **AI (planned):** simulated with **mock responses**; no external AI services in
  the MVP.
- **TypeScript throughout:** type safety required from the start.

## Development Workflow

Observed from how the project is being run (no dedicated workflow doc exists):

- Work proceeds **one task at a time**, organized as **Modules → Tasks**
  (e.g., "Module 1, Task 1.1").
- **Documentation-first:** requirements/context are written before code.
- During a task: **no commits or pushes** are made; the user reviews and
  **approves before moving to the next task**.
- The initial frontend is built against **mock data** so the UI can be built and
  demonstrated independently of a backend.

> Specific tooling (package manager, build tool, test runner, lint/format config)
> is **[UNKNOWN]** — none has been set up yet.

## Important Constraints / Guardrails

- **Privacy-first:** all personal memory data stays local; transmit nothing
  off-device; use mock/offline AI; no third-party analytics/trackers; be
  transparent to the user.
- **No application code or packages exist yet.** Nothing is implemented beyond
  documentation and Git initialization.
- **Out of scope for MVP** (see `mvp-requirements.md` §8): real AI/LLM calls, cloud
  sync, accounts/auth, teams, mobile apps, non-Chrome browsers, data import/export,
  offline AI models, monetization, analytics.

## Unknowns / Not Yet Decided

The following are **not decided or not present** and must not be assumed:

- Build tooling for React/TypeScript (e.g., Vite vs. other) — **[UNKNOWN]**.
- Extension packaging/build pipeline details — **[UNKNOWN]**.
- State management library — **[UNKNOWN]**.
- Testing framework — **[UNKNOWN]**.
- The full Module 1 task list beyond Task 1.2 — **[UNKNOWN]**.
- Any test suite, CI, or lint configuration — **[UNKNOWN]** (none exists).
