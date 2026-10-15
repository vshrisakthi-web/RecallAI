# RecallAI — Progress Log

> Running record of completed tasks. Updated after each task. No work is recorded
> here unless it has actually been done and verified. Source of truth for scope is
> `docs/mvp-requirements.md`.

---

## Module 1 — Foundation & Requirements

### Task 1.1 — Define MVP Requirements — ✅ COMPLETE

**Status:** Complete (pending nothing; documented and verified by inspection).

**What was done:**
- Created the `docs/` directory.
- Created `docs/mvp-requirements.md` documenting: product vision, target users,
  problem statement, MVP goals, planned surfaces (Chrome extension popup,
  companion side panel, web dashboard), privacy requirements, technical
  boundaries, out-of-scope features, and success criteria.
- Stated the initial frontend will use **React + TypeScript with mock data**.
- Distinguished **Planned** vs. **Implemented** items (everything app-related is
  Planned; only docs + Git are Implemented).

**Files created:**
- `docs/mvp-requirements.md`
- `docs/` (directory)

**Checks performed:**
- Confirmed `README.md` unchanged (`# RecallAI`, 1 line).
- Confirmed no application code, packages, or config were added.
- Confirmed `docs/mvp-requirements.md` exists and contains all required sections.
- `git status` reviewed: `docs/` is **untracked**; nothing was committed or pushed.

**Not implemented (still outstanding):**
- All application functionality — no React components, no mock data layer, no
  local persistence, no extension packaging, no TypeScript scaffolding.
- No packages installed; no configuration added.

---

### Task 1.2 — Define the three interfaces — ✅ COMPLETE

**Status:** Complete (documented; implementation not started, as intended for a spec task).

**What was done:**
- Created `docs/interface-specification.md` defining the three surfaces and their
  responsibilities, with a shared-vocabulary section and a **responsibility ownership
  matrix** to avoid duplication.
- **A. Chrome extension popup** — purpose, primary actions (start/pause/stop capture,
  capture current page, open companion/settings, search), content (capture status,
  current website info, recent-memory summary, privacy indicator), the three capture
  states (`active`/`paused`/`stopped`) with their shown controls, states, navigation,
  and ownership.
- **B. Companion side panel** — purpose, primary actions (contextual questions,
  conversation history, source references, related memories), content separating
  current-page context from stored memories, loading/empty/error/populated states,
  navigation, and ownership.
- **C. Web dashboard** — purpose plus five screens: **Overview, Memory Timeline,
  Ask RecallAI, Memory Detail, Privacy Settings** — each with content and states; a
  navigation map; and ownership.
- Noted the **mock-vs-real** labelling rule for Ask RecallAI (no fake live-AI backend).

**Files created:**
- `docs/interface-specification.md`

**Files updated (tracking):**
- `docs/PROGRESS.md`, `docs/PROJECT_CONTEXT.md`, `docs/NEXT_SESSION.md`

**Checks performed:**
- Confirmed alignment with `docs/mvp-requirements.md` (three surfaces, privacy-first,
  mock data) and `docs/PROJECT_CONTEXT.md` (React + TypeScript, MV3).
- No application code, packages, or configuration added (spec-only task).
- Did not modify `README.md` or `docs/mvp-requirements.md`.
- `git status` reviewed: no commit or push made yet (awaiting user approval per the
  agreed task-by-task workflow).

**Not implemented (by design):**
- No React components, no Stitch designs, no data models yet. This task only
  *specifies* the interfaces for Tasks 1.3–1.9 to build against.

---

### Task 1.3 — Generate the Overview dashboard design — ✅ COMPLETE (prompt + design; awaiting your approval)

**Status:** Prompt committed (`70988c9`). The user **generated and exported** the
Overview design → `docs/designs/overview/overview-dashboard.png` (PNG, 1211×1600,
verified openable). **Design reviewed by the agent — awaiting user approval.**

**What was done:**
- Created `docs/stitch-prompts.md` with a shared design-system context block and a
  precise Overview prompt (sidebar nav, activity summary, recent memories with source
  + privacy indicators, search entry, quick access to Ask RecallAI, capture status,
  global privacy strip).
- Added a "Pending designs" table; this milestone added an **Approved (user)** column.

**Design review (agent):**
- ✅ **Present:** sidebar nav (Overview active / Memory Timeline / Ask RecallAI /
  Privacy Settings + "🔒 Data stored locally" chip); activity summary (Total Memories,
  Captured This Week, Sources Connected, Last Ingestion); Recent Memories grid with
  source badges (Article / Web Link / Markdown Note / Code), domains, dates, "Local
  SSD" dots; Universal Context Search; "Ask RecallAI →" quick access; capture status
  (Active Capture / Pause / Halt); strong privacy indicators (Zero Cloud Telemetry,
  AES-256 GCM, "Your memories never leave this device").
- ⚠️ **Not shown / verify in Task 1.9:** **loading** and **empty (first-run)** states,
  and **tablet-width** responsiveness (single populated desktop export). Acceptable —
  the 1.3 prompt required only a populated state.
- 📌 **Task 1.9 note:** mock multi-source connections (Chrome / Obsidian / Slack /
  VS Code) and "Local Daemon Running" capture stream must stay **mock only** — real
  multi-source sync & background capture are out of MVP scope and must not imply
  granted permissions.

**Files created:**
- `docs/stitch-prompts.md`
- `docs/designs/overview/overview-dashboard.png` (design export, provided by user)

**Checks performed:**
- PNG verified: valid signature, 485 KB, 1211×1600, opens correctly.
- Compared design against `interface-specification.md` §3.1, `mvp-requirements.md`,
  and the Overview prompt (see review above).
- No application code, packages, or config added. README & mvp-requirements unchanged.

**Not approved yet:** Task 1.3 is marked **generated + reviewed**, not approved —
  approval is your decision.

> **Tasks 1.4–1.8 remain PENDING.** Their prompts are written, but no design exports
> exist yet and none have been verified. They will stay pending until you generate and
> share each export.

---

### Task 1.4 — Generate the Memory Timeline design — ✅ COMPLETE (prompt; design pending)

**Status:** Prompt written and recorded in `docs/stitch-prompts.md`. The Google
Stitch **design itself is an external, pending action** for the user.

**What was done:**
- Added a **Memory Timeline** Google Stitch prompt to `docs/stitch-prompts.md`,
  reusing the Overview design system (same sidebar, cards, badges, privacy strip).
- The prompt covers all required elements: chronological memory cards, search box,
  source-type + date filters, memory previews, opening the Memory Detail view, and
  the **populated / loading / empty / no-search-matches / error** states.
- **Updated the design-status tracking:** marked Task 1.3's prompt as *committed*
  (`70988c9`) and added a "Prompt committed" column to the Pending-designs table so
  doc status is distinct from (still-pending) design generation/export.

**Files updated:**
- `docs/stitch-prompts.md`
- `docs/PROGRESS.md`, `docs/PROJECT_CONTEXT.md`, `docs/NEXT_SESSION.md`

**Checks performed:**
- Confirmed the prompt aligns with `docs/interface-specification.md` §3.2
  (Memory Timeline states include no-search-matches).
- No application code, packages, or config added. README & mvp-requirements unchanged.

**External action required (by the user):**
- Paste the Memory Timeline prompt into Google Stitch, generate the design, export
  PNGs (populated + empty/loading/no-matches/error), save to
  `docs/designs/memory-timeline/`, and share them for Task 1.9. **No design exists yet.**

**Not implemented (by design):**
- No React component, no Stitch export, no design file. Prompt only.

---

### Task 1.5 — Generate the Ask RecallAI design — ✅ COMPLETE (prompt; design pending)

**Status:** Prompt written and recorded in `docs/stitch-prompts.md`. Google Stitch
**design is a pending user action** (generated one-by-one by the user).

**What was done:**
- Added a **Ask RecallAI (chat screen)** Stitch prompt, consistent with the Overview
  design system (same sidebar, purple/indigo "Ask RecallAI" accent card, source
  badges, "Local SSD" dots, privacy footer).
- Covers all required elements: conversation history (user bubbles + answer cards),
  question input, suggested questions (empty state), answer cards with **source
  citations/references**, and **loading / empty / error** states.
- Enforces the **mock-vs-real rule**: every answer card carries a visible
  "Mock answer" badge; no live-AI depiction.

**Files updated:** `docs/stitch-prompts.md` (+ tracking docs).

**External action required (by the user):** copy this prompt into Google Stitch,
generate, export PNG (populated + empty/loading/error), save to
`docs/designs/ask-recallai/`, share for Task 1.9. **No design exists yet.**

---

### Task 1.6 — Generate the Chrome extension popup design — ✅ COMPLETE (prompt; design pending)

**Status:** Prompt written and recorded. Google Stitch **design is a pending user action**.

**What was done:**
- Added a **Chrome extension popup** Stitch prompt as a compact ~360px card with
  **three clearly labelled states**: **ACTIVE** (green pill; Pause/Stop; current
  website info; recent captures), **PAUSED** (amber pill; Resume/Stop), **STOPPED**
  (grey pill; Start Capture).
- Included shared header (logo + lock + "Data stored locally"), "Capture this page"
  button, footer links, and accessibility notes (status as text+icon+color).
- Guardrail: only valid controls enabled per state; no unrestricted-monitoring
  implication.

**Files updated:** `docs/stitch-prompts.md` (+ tracking docs).

**External action required (by the user):** generate + export PNGs of all three
states, save to `docs/designs/extension-popup/`, share for Task 1.9. **No design exists yet.**

---

### Task 1.7 — Generate the companion side panel design — ✅ COMPLETE (prompt; design pending)

**Status:** Prompt written and recorded. Google Stitch **design is a pending user action**.

**What was done:**
- Added a **companion side panel** Stitch prompt as a narrow ~360–400px panel:
  header, a visually distinct **Current page context** card, **contextual chat**
  (composer + answer cards with source references + "Mock answer" badges), and a
  **Related memories** list.
- Covers **loading / empty / error / populated** states.
- Guardrail: clear visual separation of current-page context vs. stored memories.

**Files updated:** `docs/stitch-prompts.md` (+ tracking docs).

**External action required (by the user):** generate + export PNG (populated +
empty/loading/error), save to `docs/designs/side-panel/`, share for Task 1.9.
**No design exists yet.**

---

### Task 1.8 — Generate Memory Detail + Privacy Settings designs — ✅ COMPLETE (prompt; design pending)

**Status:** Prompts written and recorded. Google Stitch **designs are a pending user action**.

**What was done:**
- Added two Stitch prompts:
  - **8a Memory Detail** — title + "← Back to Timeline", content, source block
    (badge + title + clickable source link + domain), metadata (date, tags,
    "Local SSD", vector/OCR fields), delete action; states populated/loading/error.
  - **8b Privacy Settings** — local-processing banner, capture preferences with
    plain-language privacy explanations, capture status & controls, excluded /
    sensitive-page handling, memory deletion controls, and a confirmation dialog for
    destructive actions. Guardrail: no implication of granted/unrestricted permissions.

**Files updated:** `docs/stitch-prompts.md` (+ tracking docs).

**External action required (by the user):** generate + export PNGs of both screens,
save to `docs/designs/memory-detail/` and `docs/designs/privacy-settings/`, share for
Task 1.9. **No designs exist yet.**

---

---

### Milestone — Overview approved + designs 1.4–1.7 generated & organized

**Status:** Done (organization + status recording). **Overview (1.3) approved by the
user.** The user generated four more Stitch designs and dropped them into
`docs/designs/overview/`; the agent verified each PNG's content matches its filename
and **moved** each into its own directory (original bytes preserved, nothing
overwritten or deleted).

| Task | Export path | Dims | Status |
| ---- | ----------- | ---- | ------ |
| 1.3 Overview | `docs/designs/overview/overview-dashboard.png` | 1211×1600 | ✅ **Approved** |
| 1.4 Memory Timeline | `docs/designs/memory-timeline/memory-timeline.png` | 922×1600 | 🟡 Generated — needs review |
| 1.5 Ask RecallAI | `docs/designs/ask-recallai/ask-recallai.png` | 980×1600 | 🟡 Generated — needs review |
| 1.6 Chrome popup | `docs/designs/extension-popup/extension-popup.png` | 2560×1542 | 🟡 Generated — needs review |
| 1.7 Companion side panel | `docs/designs/side-panel/side-panel.png` | 2560×7278 | 🟡 Generated — needs review |
| 1.8 Memory Detail | — | — | ⬜ **MISSING — user must generate** |
| 1.8 Privacy Settings | — | — | ⬜ **MISSING — user must generate** |

**Not approved merely for existing:** Tasks 1.4–1.7 are recorded as **generated, not
approved** — they still need your review. Task 1.8 has **no exports** and must be
generated in Google Stitch (prompts 8a/8b are ready in `docs/stitch-prompts.md`).

**State-coverage to confirm on review:** 1.6 popup (wide image — confirm Active/Paused/
Stopped all present); 1.7 side panel (very tall image — confirm loading/empty/error
present). Exact missing exports for 1.8 are the two screens named above.

---

### Task 1.9 — Implement the frontend — ✅ COMPLETE (build + lint + tests pass)

**Status:** Done and verified. React + TypeScript (Vite) + Tailwind app implementing all
seven surfaces with typed mock data. **Build, lint, and 13 tests all pass.**

**What was built (all mock data, no backend):**
- **Scaffold:** Vite + React 18 + TypeScript (strict) + Tailwind CSS + React Router +
  Vitest + React Testing Library + ESLint. Config: `package.json`, `vite.config.ts`,
  `tsconfig*.json`, `tailwind.config.js`, `postcss.config.js`, `.eslintrc.cjs`,
  `index.html`.
- **Data layer (separate from UI):** `src/data/types.ts` (Memory, CaptureState, ChatTurn,
  SourceReference, CurrentPageContext, PrivacySettings) and `src/data/mockData.ts`
  (6 memories, activity summary, suggested questions, `mockAsk()`, seed conversation,
  page context, default settings). Components import from here — swap for API calls later.
- **Shared components:** `AppLayout` (sidebar + privacy bar + footer), `MemoryCard`,
  `SourceBadge`, `StatCard`, `UIStates` (Loading/Empty/Error/NoMatches).
- **Dashboard screens:** **Overview** (activity summary, search + source filters,
  Ask quick-access, capture status, recent memories), **Memory Timeline** (search +
  source + date filters, no-matches state), **Ask RecallAI** (chat history, composer,
  suggested questions, source citations, loading/error), **Memory Detail** (content,
  source link, metadata, delete with confirmation, not-found error), **Privacy Settings**
  (capture prefs, excluded patterns, deletion controls, save).
- **Extension surfaces (isolated routes):** **Extension popup** (`/popup`) with
  Active/Paused/Stopped states + capture-this-page; **Companion side panel** (`/panel`)
  with distinct current-page context, contextual chat, source references, related memories.
- **State:** `src/state/MemoriesContext.tsx` — deleting a memory reflects across screens.
- **Mock-AI labelling:** every Ask/panel answer carries a visible **"Mock answer"** badge.

**Design dependency (honest status):** Overview, Memory Timeline, Ask RecallAI, extension
popup, and side panel follow the **provided Stitch exports**. **Memory Detail and Privacy
Settings have no Stitch export (Task 1.8 pending)** — those two screens are built from
`docs/interface-specification.md` and recorded as pending design.

**Files created:** 10 config files + `src/**` (23 files: 2 data, 5 components, 7 pages,
1 state, 1 layout, 1 lib, 1 css, 1 main/App, 4 tests + setup).

**Verification:** `npm run build` exit 0 (tsc strict + Vite, 49 modules); `npm run lint`
exit 0 (`--max-warnings 0`); `npm test` → **13 passed / 4 files**; production preview served
HTTP 200 for index + JS asset.

---

### Task 1.10 — Test and verify the UI — ✅ COMPLETE

**Status:** Done. All configured commands pass.

**Commands executed (actual results):**
- `npm run build` → **exit 0** — TypeScript strict compile + Vite production build
  (`dist/index.html` 0.57 kB, CSS 20.65 kB, JS 213.19 kB; 49 modules; built in ~0.9s).
- `npm run lint` → **exit 0** — ESLint, 0 errors / 0 warnings (`--max-warnings 0`).
- `npm test` → **exit 0** — Vitest: **4 test files, 13 tests passed** (Overview search,
  mock-answer labelling + append + error; popup Active→Paused→Stopped→restart; Memory
  Detail content / not-found error / delete confirmation).
- `npm run preview` + `curl` → index.html and JS asset both **HTTP 200**; title correct.

**What the tests + manual checks cover:**
- **Navigation:** all dashboard routes wired via React Router; memory cards open
  `/memory/:id`; popup/panel are isolated routes; back links present.
- **Capture-state transitions:** popup Active↔Paused↔Stopped verified in tests.
- **Search & filters:** Overview + Timeline search and source/date filters (tested).
- **Mock chat:** Ask/panel append a labelled mock answer; error state simulated.
- **Memory detail / delete:** content renders, unknown id shows error, delete asks
  confirmation.
- **UI states:** Loading (Memory Detail brief load), Empty (no memories / no matches),
  Error (not-found, simulated assistant failure), No-matches (Timeline), Populated.
- **Responsive:** layout uses responsive Tailwind classes (sidebar collapses on small
  screens; grids reflow sm/lg); popup/panel are fixed-width cards.
- **Quality:** no TypeScript errors, no lint warnings, no failing tests; React Router
  v7 future-flag warnings silenced via `future` props.

**Known limitations (honest):**
- No automated **visual/responsive** regression tests — responsive behaviour uses
  Tailwind classes and was checked structurally, not pixel-tested across devices.
- Console-error check was done via the build/test/preview runs, not an interactive
  browser session.
- Memory Detail + Privacy Settings still lack Stitch design exports (Task 1.8).

---

## Module 2 — Chrome Extension & Capture Engine

### Task 2.1 — Create the Manifest V3 extension — ✅ COMPLETE (code + build)

**What was done:**
- `extension/manifest.json` — MV3, name RecallAI, `minimum_chrome_version` 102,
  popup `popup/popup.html`, background service worker
  `background/serviceWorker.js`, icons 16/48/128, permissions
  `["activeTab","scripting","storage"]`, `host_permissions: []`,
  CSP `script-src 'self'; object-src 'self'`.
- Reproducible build: `npm run build:extension` = icons → popup (Vite+React+
  Tailwind) → content (IIFE) → background (IIFE) → `assemble.mjs` →
  `verify-dist.mjs`. Produces `extension/dist-extension/` (git-ignored).

**Verified:** `npm run build:extension` **exit 0**; verify step reports valid MV3,
all referenced files present, popup assets wired, minimal permissions,
no `host_permissions`, CSP locked to self.

**Not done:** the extension has **not** been installed/loaded in Chrome by me —
`docs/module-2-chrome-extension.md` gives the Load-unpacked steps + a manual
checklist. Live browser verification is the user's step.

---

### Task 2.2 — Icons + popup entry point — ✅ COMPLETE (build-time)

**What was done:**
- `extension/scripts/gen-icons.mjs` — dependency-free PNG encoder writes valid
  `assets/icon{16,48,128}.png` (RecallAI mark).
- `extension/popup/` — React popup (`Popup.tsx`, `index.tsx`, `popup.html`,
  `popup.css`) matching the approved design language at ~360px wide: branding,
  active-tab title + domain, capture-state pill (Active/Paused/Stopped), Capture
  button (+ "Capture only my selected text"), Pause/Resume/Stop controls,
  recent-captures list, and a privacy footer. No placeholder links.

**Verified:** icons generated; popup builds to `dist-extension/popup/popup.html`
with wired JS/CSS; Tailwind utilities present (CSS ~9.2 kB, `crossorigin`
stripped for extension pages).

---

### Task 2.3 — Minimum permissions — ✅ COMPLETE

`activeTab` + `scripting` + `storage` only; **no** `host_permissions`, no
tabs/history/cookies/downloads. Injection is user-triggered via
`chrome.scripting.executeScript` on the active tab. Restricted pages
(`chrome://`, Web Store, PDF viewer, `chrome-extension://`) are detected and
rejected with a clear message (verified by `domain.test.ts`). No bypass of
Chrome security; no background surveillance.

---

### Task 2.4 — Detect the active tab — ✅ COMPLETE

`getActiveTab()` → `chrome.tabs.query({active:true,currentWindow:true})` (no
`tabs` permission needed). Captures title, url, derived domain; timestamp added
when the record is created (`buildRecord`). Missing tab → `NO_TAB`. Domain
derivation + restricted detection unit-tested (`domain.test.ts`).

---

### Task 2.5 — Extract permitted readable text — ✅ COMPLETE (unit-tested)

`extension/lib/extract.ts`:
- Removes `script/style/nav/footer/aside/form/button/input/...` chrome; prefers
  `<article>`/`<main>`; preserves headings + paragraphs; strips blank runs.
- **Hard cap** `MAX_TEXT_LENGTH` (20,000 chars) — truncation flagged via
  `truncated: true`.
- Preserves source url + title (record built in `capture.ts`).
- Empty pages → `{ status: 'empty', note }`. No content is uploaded.
- **Never reads form/password/input values** (removed before capture — asserted
  in `extract.test.ts`).
- **YouTube:** flagged by `isYouTubeUrl`; only title/url + visible text captured;
  transcript is **not** claimed; record marked `partial` with an explicit note.

**Fixtures/tests:** `article.html`, `docs.html`, `empty.html`, `youtube.html`
driving `extract.test.ts` (A, B, E, size-limit cases).


---

### Task 2.6 — User-triggered capture — ✅ COMPLETE (unit-tested)

Capture flow in `serviceWorker.ts` `CAPTURE` case: check state → reject if
Paused/Stopped → reject restricted → inject content script → extraction → build
record → save → success summary. Repeated clicks disabled in the popup
(`phase==='capturing'` guard) and duplicate content de-duped in the repository
(storage test). Handles empty pages, unsupported pages, injection failures,
storage errors, missing tab.

---

### Task 2.7 — Capture selected text with context — ✅ COMPLETE (unit-tested)

`EXTRACT_SELECTION` returns selected text + the surrounding block
(`findSurroundingContext` walks up to `p/li/h*/blockquote/td/pre`). Records are
typed `selection` with `selectedText` + `surroundingContext`. If nothing is
selected the worker returns `EMPTY` with guidance to use a full-page capture —
it never silently substitutes a full-page capture.

---

### Task 2.8 — Capture states — ✅ COMPLETE (unit-tested)

`extension/lib/state.ts` state machine: `active` (capture allowed),
`paused` (rejected, resume available), `stopped` (disabled, start available).
Valid transitions + `canCapture` unit-tested (`state.test.ts`). State persisted
via `chrome.storage.local` (`loadState`/`saveState`, storage test) so the popup
reflects the real state after close/reopen. Active = user may capture; it is
**not** continuous monitoring.

---

### Task 2.9 — Message bridge + local storage — ✅ COMPLETE (unit-tested)

- Typed contracts + `isValidMessage` guard in `lib/messages.ts`; invalid messages
  rejected (`messages.test.ts`).
- `CaptureRepository` over `chrome.storage.local`: save, recent(limit), byId,
  delete, state load/save, content de-dup, storage-error handling
  (`storage.test.ts`).
- `CaptureRecord` model per spec (id/title/url/domain/capturedAt/captureType/
  extractedText/selectedText?/surroundingContext?/status/note?/contentLength).
- Optional **local backend adapter** (`lib/backend.ts`): disabled by default,
  **localhost-only**, non-fatal; never uploads by default (`backend.test.ts`).

---

### Task 2.10 — Testing — ✅ COMPLETE (automated) / 🟡 manual pending

**Automated (actual results):**
- `npm run build` → **exit 0** (dashboard unaffected).
- `npm run typecheck:extension` → **exit 0** (strict TS incl. `@types/chrome`).
- `npm run lint` → **exit 0** (`--max-warnings 0`; extension dist/scripts ignored,
  `chrome` global declared for `extension/**`).
- `npm test` → **exit 0 — 11 files, 44 tests passed** (Module 1: 6 files/13 tests
  still pass; Module 2: extract A/B/E, state, capture, storage, messages,
  domain, backend).
- `npm run build:extension` → **exit 0**; verify step green.

**Manual Chrome verification — NOT done by me (no browser automation here):**
the exact click-through is in `docs/module-2-chrome-extension.md`
("Manual verification checklist"). Required user actions: Load unpacked
`extension/dist-extension`, capture a blog/docs page, test selection, Pause/
Stop block + Resume/Start restore, state persists across popup close, restricted
page message, YouTube partial-record note.


---

## Module 3 — Backend Ingestion Pipeline (FastAPI)

Guide: `docs/module-3-ingestion-pipeline.md`. **All automated steps verified.**

### Task 3.1 — FastAPI app, config, error envelope, request-id — ✅ COMPLETE

`app/main.py` `create_app()`: request-id middleware (first), optional CORS
(off unless `RECALLAI_CORS_ORIGINS` set), routers under `/api/v1`, and four
exception handlers (validation 422, storage 500, unhandled 500, not-found 404)
all returning the shared `{"error":{code,message,details,request_id}}` envelope
with **no internals leaked**. `app/core/config.py` holds documented, env-tunable
limits (`RECALLAI_*`); `app/core/errors.py` builds the envelope; `X-Request-ID`
is assigned/echoed and unsafe client ids rejected (`400 INVALID_REQUEST_ID`).

### Task 3.2/3.4 — Schemas + validation — ✅ COMPLETE

`app/schemas/`: `common` (CanonicalRecord + SourceType/CaptureType/ExtractionStatus
enums), `browser` (`BrowserCaptureIn`, camelCase), `transcript` (`TranscriptIn`),
`note` (`NoteIn`). All use `extra=forbid` and field/model validators for URL
scheme + domain-host match, **timezone-aware timestamps** (naive rejected, future
skew + min-year guards), size caps, non-empty text, and bounded metadata
(≤50 keys, scalars, depth ≤2). A validation failure → `422` and **nothing is
persisted** (no partial records).

### Task 3.5 — Normalization + hashing — ✅ COMPLETE

`app/services/normalize.py` is deterministic: line-ending normalization,
indentation preservation (code blocks survive), internal whitespace collapse,
blank-run collapse, whole-text trim. `app/services/hashing.py` = SHA-256 of
normalized text. Same input → same output → stable content hash.

### Task 3.6 — Deduplication — ✅ COMPLETE

Dedup key = `source_type + source_url + capture_type + content_hash` (title
**excluded**). Same URL+content → duplicate (`200`, existing id); changed content
→ new record (`201`); distinct notes with the same title are not merged. Title is
never part of the key.

### Task 3.7/3.8 — Routes + persistence — ✅ COMPLETE

`GET /api/v1/health`; `POST /api/v1/ingest/{browser,transcript,notes}`. Responses
return `duplicate`, `status`, `message`, `record_id`, `source_type`,
`content_hash`, and the full `record`. `app/repositories/base.py` defines the
swappable `IngestionRepository` + `StorageError`; `json_store.py` implements it
with a JSON file (`backend/data/ingested.json`), atomic temp-file writes, and a
thread lock (**single-process safe only**).

### Task 3.9 — Middleware, CORS, error responses — ✅ COMPLETE

Request-id middleware + optional explicit CORS (off by default) + the structured
error envelope (see 3.1). Storage/unhandled failures log full detail server-side
and return only a safe message.

### Task 3.10 — Testing — ✅ COMPLETE (automated)

**Actual: `cd backend && .venv/bin/python -m pytest` → 59 passed** (2026-10-11).
Covers normalize, repository (dedup + persistence + restart), each endpoint's
happy path + every validation rule, health/request-id/envelope, and simulated
storage failure. **Regression checks still green:** `npm test` (44), `npm run
lint`, `npm run build`, `npm run typecheck:extension`, `npm run build:extension`.

### Task 3.11 — Extension adapter compatibility — ✅ VERIFIED (no change needed)

`BrowserCaptureIn` accepts exactly the extension's 12-field `CaptureRecord`
(camelCase). `extension/lib/backend.ts` remains **disabled by default**,
localhost-only, and non-fatal — **no adapter change was required.** (Edge: an
`empty`/`error` capture with no text is rejected by design.)

### Live smoke test (manual, uvicorn on :8099)

`GET /api/v1/health` → `200 {"status":"ok","version":"0.3.0"}` with
`X-Request-ID`. Browser/transcript/note posts → `201` with normalized text
(whitespace collapsed) + `X-Request-ID` echoed; identical re-posts → `200`
duplicate; `/docs` → `200`; a bad URL → `422` `VALIDATION_ERROR` envelope.

---

## Module 4 — Structured Memory

**Status: implementation and automated verification complete.** The local Module 3
backend files were untracked before this work and remain uncommitted; do not assume
they are part of `origin/main`. The default JSON file was checked before activation
and did not exist, so no records required migration.

### Tasks 4.1–4.3 — SQLite, schema, migrations — ✅ COMPLETE

- Declared SQLAlchemy 2.x and Alembic in `backend/requirements.txt`.
- Repaired SQLAlchemy models and added `sources`, `memories`, `conversations`, and
  `tasks`. Memories preserve Module 3's source/capture fields and use a database
  uniqueness constraint for idempotency. Sources are shared for the same source type
  and URL; deleting a memory retains its source.
- `RECALLAI_DB_PATH` configures the SQLite file; default is
  `backend/data/recallai.db`. Foreign keys are enabled by the engine. The database,
  journal, WAL and SHM files are Git-ignored.
- Added Alembic revision `20261011_0001`; FTS5 is created when available. Tests also
  exercise a migration without FTS5 to cover the `LIKE` fallback.
- Migration verification: clean upgrade, repeat upgrade over a populated DB,
  foreign keys, rollback, corrupt DB handling, and persistence from a new engine.

### Tasks 4.4–4.6 — Repositories and ingestion — ✅ COMPLETE

- `MemoryRepository` and `SourceRepository` centralize SQLite persistence and queries.
- Existing Module 3 validation, normalization, hashing, deduplication, response
  records and request IDs are retained; FastAPI now uses SQLite as its primary store.
- Added an explicit repeatable JSON importer. It validates records, reports
  imported/duplicate/skipped counts, and never changes its source file. No default
  `backend/data/ingested.json` was present during inspection.

### Tasks 4.7–4.9 — Search, filters, memory/source APIs — ✅ COMPLETE

- Added FTS5 title/content/source-title/domain indexing with insert/update/delete
  triggers and safe query bindings; case-insensitive `LIKE` fallback is covered.
- List filtering supports `q`, `from_date`, `to_date`, exact normalized `domain`,
  `source_type`, `page`, and `page_size`. Date-only boundaries are UTC calendar
  days, with `to_date` inclusive. Ordering is deterministic.
- Added paginated list, detail, source lookup, and safe memory deletion. Deleting a
  shared memory does not delete its source. Validation, missing-resource, and
  framework-generated 404s retain the standard request-ID error envelope.

### Task 4.10 — Real Timeline and Detail — ✅ COMPLETE (Chrome manual step pending)

- Timeline loads API data, supports text/date/domain/source filters and pagination,
  cancels obsolete requests, and distinguishes loading, empty, no-match and retryable
  error states. It never substitutes mock records on API failure.
- Detail loads saved content/source metadata and deletes only after confirmation;
  successful deletion returns to a refreshed Timeline.
- The extension remains local-first. Its popup now offers explicit opt-in to send
  future captures to `127.0.0.1:8000`; Chrome asks for one optional localhost origin.
  Default behavior remains local storage only.
- Live local browser/API smoke test: created one browser capture, one transcript and
  one manual note through FastAPI; saw all three in Timeline; searched and applied
  combined date/domain/source filters; opened real detail/source; deleted the browser
  record and confirmed it no longer matched search; restarted FastAPI and verified the
  other two records persisted.
- **Not verified:** loading the extension in Chrome, approving the optional permission,
  and performing the actual Chrome capture click. This remains a user manual check.

### Module 4 Verification

- `cd backend && .venv/bin/python -m pytest` → **76 passed** (one existing
  `python-multipart` deprecation warning).
- `npm test` → **50 passed** (12 files; existing React Router future-flag warnings).
- `npm run lint` → exit 0; installed TypeScript 5.9.3 exceeds the configured
  typescript-eslint parser support range and emits a compatibility warning.
- `npm run build`, `npm run typecheck:extension`, `npm run build:extension` → all
  exit 0; MV3 permission verifier passes.
- Fresh local development database initialized using `alembic upgrade head` and is
  ignored by Git. No commit or push was made; review the current status before
  choosing how to separate the pre-existing Module 3 work from Module 4.

---

## Module 5 — AI-Powered Summarization

### Task 5.1 — Inspect project and verify requirements — ✅ COMPLETE (read-only)

- Confirmed the active flow is React/Vite → FastAPI → SQLAlchemy/SQLite; captured
  webpage text is available as `Memory.normalized_content` through the memory
  repository. The frontend API helper and Memory Detail provide existing UI/request
  patterns.
- Backend runtime is Python 3.9.6; dependencies are pinned in
  `backend/requirements.txt`. No LLM provider or summarization endpoint exists.
- Current Uvicorn installation supports `--env-file` and `python-dotenv` is already
  present through the existing backend environment. `backend/.env.example` did not
  exist before this task; `.env` is already ignored by Git.
- Decision for the next implementation step: use Gemini hosted inference, with the
  existing `httpx` dependency unless later work shows a provider SDK is necessary.
  Hosted summarization will require internet and will send the selected memory text
  to Google only after a user action and clear disclosure.

### Task 5.2 — Configure the LLM provider — ✅ COMPLETE

- Added backend-only `RECALLAI_GEMINI_API_KEY`, `RECALLAI_GEMINI_MODEL`,
  `RECALLAI_GEMINI_TIMEOUT_SECONDS`, and `RECALLAI_MAX_SUMMARY_INPUT_CHARS` settings.
- Default model is `gemini-3.8-flash` (Google's stable model listed in its current
  Gemini model documentation). Timeout and input-size limits are bounded and invalid
  values fail with a named configuration error. Missing credentials do not prevent
  the non-AI backend from starting; `Settings` redacts the key from its repr.
- Added `backend/.env.example` with an empty key value and local-only instructions.
  No secret was requested, stored, or included in the template. Existing `httpx` is
  sufficient for the planned REST client; no dependency was added.
- Focused verification: `cd backend && .venv/bin/python -m pytest tests/test_config.py`
  → **7 passed**. Full regression: `cd backend && .venv/bin/python -m pytest` →
  **83 passed** (one existing multipart deprecation warning). A keyless app import and
  synthetic environment/redaction smoke checks also passed. No Gemini request was made.

### Task 5.3 — Implement the AI service — ✅ COMPLETE (no live provider call)

- Added `GeminiSummarizationService` using the existing `httpx` dependency and
  Gemini's stateless `generateContent` REST method. No provider SDK or other
  dependency was added.
- The method accepts one text value, rejects empty or over-limit input before
  transport, and sends only that text. A system instruction treats page content as
  untrusted data and asks for a concise factual bullet summary without following
  embedded instructions. No URL, source metadata, or memory list is sent.
- Returns a validated `{summary, model}` schema; key remains in a request header and
  is never included in the URL or logged by the service. Provider HTTP/timeout mapping
  and formal mocked provider tests remain in Tasks 5.4 and 5.6.
- Verification: module `py_compile` and synthetic injected-transport request/response
  smoke passed; empty/oversize smoke confirmed the transport is not called; full
  backend suite → **83 passed**. No real key or external Gemini request was used.

### Task 5.4 — Isolated service tests with a mocked HTTP transport — ✅ COMPLETE

- Added `backend/tests/test_summarization.py` (16 tests). Every test injects a
  fake `post` transport through the service's existing constructor hook, so the
  suite performs **no network requests and needs no real API key**.
- Coverage: successful summary and model echo; exact Gemini endpoint URL with the
  key sent only in the `x-goog-api-key` header (never in the URL); configured
  timeout; request body contains the source text plus the prompt-injection guard
  system instruction; empty/whitespace/non-string/oversized input rejected before
  the transport is called (asserted via zero recorded calls) while input at the
  exact limit is accepted; missing `RECALLAI_GEMINI_API_KEY` raises before any
  request; provider HTTP 401 propagates as `httpx.HTTPStatusError`; malformed,
  text-less, whitespace-only, and non-JSON responses raise
  `SummaryResponseError`; transport-level `ConnectError` propagates to the caller.
- Verification: `cd backend && .venv/bin/python -m pytest
  tests/test_summarization.py` → **16 passed**. Full regression → **99 passed**
  (83 existing + 16 new; one pre-existing `python-multipart` deprecation
  warning). No external Gemini request was made at any point.

### Module 4 re-verification (same session)

- A fresh end-to-end run against a **temporary** database
  (`RECALLAI_DB_PATH=/tmp/...`, port 8010, real uvicorn process) passed
  **26/26 checks**: fresh migration, browser/transcript/note ingestion → 201,
  rows visible in the SQLite file, duplicate re-post → 200 `duplicate=true`,
  search, date/domain/source filters, invalid-range → 422, pagination,
  detail + source lookup, missing ID → 404, delete → 200 then 404 and row
  removed from the DB file, and persistence + dedupe after a server restart.
  Temporary databases were deleted afterwards; `backend/data/recallai.db` was
  not touched.

### Task 5.5 — Summarization API endpoint — ✅ COMPLETE (no live provider call)

- Added **`POST /api/v1/memories/{memory_id}/summary`** on the existing memories
  router (`backend/app/api/routes/memories.py`). It loads the memory through the
  repository layer, returns a 404 envelope when absent, passes **only** the
  memory's `normalized_text` to the existing `GeminiSummarizationService`, and
  responds with `{memory_id, summary, model}`
  (`MemorySummaryResponse` in `app/schemas/summarization.py`).
- New `get_summarization_service()` dependency in `app/api/deps.py` lets tests
  substitute the provider boundary. No database schema change or migration was
  needed; ingestion, search, deletion, browser-extension behavior, and the
  frontend were untouched.
- Error handling reuses the shared envelope via the existing HTTPException
  handler: **404** `NOT_FOUND` (memory missing), **422** `VALIDATION_ERROR`
  (empty stored text; service input-limit rejection), **503**
  `PROVIDER_NOT_CONFIGURED` (new `GeminiConfigError`, a `RuntimeError` subclass,
  raised by `require_gemini_api_key` — Task 5.2 tests still pass unchanged),
  **502** `PROVIDER_ERROR` (provider HTTP/connect failure or unusable provider
  response), **504** `PROVIDER_TIMEOUT`. `main.py`'s status→code mapping gained
  502/503/504 entries; 404/422/default behavior is unchanged.
- Privacy: the endpoint accepts no client credentials (a stray request body is
  ignored), the key travels only in the provider request header and never
  appears in responses, and only the memory's text is sent — no URLs, titles,
  metadata, other memories, or logged page content.
- Added `backend/tests/test_summary_api.py` (**12 tests**), all mocking the
  service dependency or injecting a fake `post` transport; a `_forbidden_post`
  transport fails any test that would contact a provider. Coverage: success
  schema/status, exact stored text passed (URL/title/domain stay local), a
  real-service run proving only the text leaves the app and the key stays out of
  the response, client-supplied `api_key` body ignored, 404 envelope with
  request-id correlation, empty stored text rejected before the provider is
  called, oversized stored text rejected before transport, 503 missing config,
  504 timeout, 502 connect error and malformed provider response, plus
  regression of detail/list/delete endpoints.
- Verification: focused `pytest tests/test_summary_api.py` → **12 passed**;
  full backend suite from `backend/` → **111 passed** (99 existing + 12 new;
  one pre-existing `python-multipart` deprecation warning);
  `git diff --check` clean. **No real Gemini request was made.** Nothing was
  staged, committed, or pushed.

**Next task:** 5.6 — architecture correction toward the local-LLM goal; see below.

### Task 5.6 — Switch the summary endpoint to a local Ollama model — ✅ COMPLETE (no live model run)

- **Architecture review first (user request):** inspection confirmed that Task 5.5
  called the **cloud** Gemini API — `GeminiSummarizationService` posts to
  `https://generativelanguage.googleapis.com/...` with an `x-goog-api-key`
  header — which violated Module 5's offline-LLM goal. Ollama had **not** been
  configured in any earlier task (no Ollama reference exists anywhere in the
  backend), so a local provider had to be introduced; this was reported to the
  user with the explanation before any code changed. The Gemini service, its
  Task 5.2 config, and all Task 5.3/5.4/5.5 tests were preserved untouched.
- Added loopback Ollama settings in `app/core/config.py`:
  `RECALLAI_OLLAMA_BASE_URL` (default `http://127.0.0.1:11434`),
  `RECALLAI_OLLAMA_MODEL` (default `llama3.2`), `RECALLAI_OLLAMA_TIMEOUT_SECONDS`
  (default 30, bound 120), reusing `RECALLAI_MAX_SUMMARY_INPUT_CHARS`. New
  `OllamaConfigError(RuntimeError)` plus `Settings.require_ollama_base_url()`,
  which **rejects any non-loopback or scheme-less URL before a request is
  made** — memory text structurally cannot reach a cloud host, even under
  misconfiguration.
- Added `OllamaSummarizationService` (`app/services/summarization.py`) with the
  same `summarize()` contract: `POST {loopback}/api/chat`, `stream: false`,
  system + user messages carrying only the memory's `normalized_text` and the
  existing prompt-injection guard, `temperature 0.2` / `num_predict 512`, and
  **no credentials of any kind**. New `SummaryModelUnavailableError` covers an
  unreachable daemon (connection refused) and an un-pulled model (HTTP 404).
- `get_summarization_service()` (`app/api/deps.py`) now returns the Ollama
  service, so the endpoint workflow is: SQLite memory → summary API → local
  Ollama → summary → response. `main.py` and `MemorySummaryResponse` needed no
  changes; request-ID and error-envelope conventions are unchanged.
- Error mapping on `POST /api/v1/memories/{id}/summary`: **404** missing
  memory, **422** empty/oversized text (rejected before any transport call),
  **503** `PROVIDER_NOT_CONFIGURED` (non-loopback URL, daemon unreachable,
  model not pulled), **504** timeout, **502** other transport errors and
  unusable/invalid model responses.
- Tests (all mocked — no running model, no network, no credentials): new
  `backend/tests/test_ollama_summarization.py` (**19 tests**: payload shape,
  loopback URL, credential-free headers, input limits, 404/connect →
  unavailable, timeout/HTTP-error propagation, invalid responses, parametrized
  non-loopback rejection before transport) and `test_summary_api.py` updated to
  **14 tests** (real-service loopback/credential-free outbound assertions;
  new 503 cases for model unavailable, daemon unreachable, and non-loopback
  URL; all other Task 5.5 cases retained).
- Docs updated: `backend/.env.example`, `README.md`, `docs/NEXT_SESSION.md`,
  `docs/PROJECT_CONTEXT.md`.
- Verification: focused summary tests
  (`tests/test_ollama_summarization.py` + `tests/test_summary_api.py`) →
  **33 passed**; with the retained Gemini/config regression files → **56
  passed**; full backend suite → **132 passed**; `git diff --check` clean.
  **Ollama is not installed on this machine, so no live local-model run was
  performed** — offline operation is verified only at the unit level (outbound
  requests pinned to loopback by assertion and by `require_ollama_base_url`).
  Nothing was staged, committed, or pushed.

### Task 5.7 — Local Ollama setup and live inference — DONE (2026-10-11)

- Environment: macOS (Apple Silicon), 24 GB RAM; Ollama was absent. Installed
  **Ollama 0.40.3** via `brew install ollama` (user-approved ~1.3 GB model
  download also approved); daemon kept alive with `brew services start ollama`
  (listens on 127.0.0.1:11434). Model **`llama3.2:1b`** pulled (≈1.3 GB,
  chosen over `llama3.2` for RAM headroom; summaries verified adequate).
- `backend/.env` created (Git-ignored, `git check-ignore` verified) with
  `RECALLAI_OLLAMA_MODEL=llama3.2:1b` — the config default `llama3.2` does not
  match the pulled model, so the env pin matters. Caught live: starting
  uvicorn **without** `--env-file .env` yields an instant 503 because the
  model name then falls back to `llama3.2`.
- Live inference: direct `POST /api/chat` returned real text; full pipeline
  (synthetic photosynthesis memory `mem_e35bfbd36b80a75901724b77`, no personal
  data) → `POST /api/v1/memories/{id}/summary` returned
  `{"memory_id", "summary", "model": "llama3.2:1b"}` in ~3.3 s. Error paths
  live-checked: 404 missing memory, repeat request → 200 fresh summary, dead
  loopback daemon → 503 safe envelope, 422 validation envelope with
  `X-Request-ID` echo.

### Task 5.8 — Frontend AI summary integration — DONE (2026-10-11)

- `src/lib/memoriesApi.ts`: added `MemorySummary` type and `summarizeMemory()`
  (POST to `/api/v1/memories/{id}/summary`, optional `AbortSignal`, backend
  error-envelope messages surfaced as-is, raw network failures rewritten to
  plain language). No API key ever sent from the browser.
- `src/pages/MemoryDetail.tsx`: user-initiated **“Generate AI Summary”**
  section under the memory content — loading state (`role="status"`),
  rendered summary + actual model id + “stays on this device” note, error
  alert, regenerate option, duplicate-click guard (disabled button + handler
  guard), and an id-change effect that aborts in-flight requests so a stale
  response for a previously viewed memory can never display. No automatic
  summarization anywhere.
- `src/test/MemoryDetail.test.tsx`: mock factory extended; 4 new tests
  (success + model display, loading + duplicate-click prevention, backend
  error message + retry, stale-response discard across in-place navigation to
  a second memory). Fixed two test bugs during development: duplicated
  `render()` call and cross-test mock call-count accumulation
  (`vi.clearAllMocks()` in `beforeEach`).

### Task 5.9 — E2E testing and privacy verification — DONE (2026-10-11)

- Backend automated: full suite **132 passed** (mocked, no daemon required);
  focused files confirm coverage of valid/missing/empty/oversized/duplicate
  requests, model & daemon unavailability, timeout, invalid provider
  responses, request-ID propagation, and error-envelope formatting.
- Frontend automated: **54 passed** (`npm test`, includes the 4 new summary
  tests and the 4 extension test files), `npm run lint` clean,
  `npx tsc -b --noEmit` clean, `npm run build` OK, `git diff --check` OK.
- Privacy inspected + tested: no runtime route/dep imports
  `GeminiSummarizationService` (grep across `backend/app`; only its own
  legacy tests reference it); loopback enforcement rejects non-loopback URLs
  before any transport; Ollama payload contains only model/messages/options —
  no credentials; the summarization service has no logger (memory text never
  logged); system instruction treats captured text as untrusted
  (prompt-injection safeguard); browser sends no API keys; extension
  capture-consent code untouched.
- Live E2E (backend): verified as in Task 5.7 with real uvicorn + real Ollama.
- **Not verified:** fully offline run (would require disabling this machine's
  internet — not done without user action) and a scripted browser click
  through (no browser-automation tooling in the repo). Manual UI steps are in
  `docs/module-5-local-ai-summarization.md`.

### Task 5.10 — Final hardening and Module 5 completion — DONE (2026-10-11)

- Review: Module 5 changes inspected for correctness, error handling, type
  safety, timeouts, privacy, and duplication — no defects found beyond the
  documentation drift fixed below (model name default vs. pulled model,
  `--env-file` requirement called out explicitly).
- Verification commands executed (results above): backend
  `.venv/bin/python -m pytest -q` → 132 passed; frontend `npm test`, `npm run
  lint`, `npx tsc -b --noEmit`, `npm run build`, `git diff --check` → all
  green. Extension tests run inside the root vitest suite (4 files).
- Docs updated: `README.md` (Module 5 section: install, model choice,
  `--env-file`, UI button, live verification, troubleshooting pointers),
  new `docs/module-5-local-ai-summarization.md`, `docs/NEXT_SESSION.md`,
  `docs/PROJECT_CONTEXT.md`, this entry.
- Git safety: nothing staged/committed/pushed; `backend/.env`,
  `backend/data/*.db`, `dist/`, `node_modules`, and Ollama model blobs
  (stored under `~/.ollama`, outside the repo) are all excluded from Git.
  Pre-existing state preserved: the whole `backend/` tree and several
  frontend/docs files remain uncommitted local work awaiting the user's
  review.

**Module 5 status:** functionally complete with live local inference verified
on this machine. The only outstanding acceptance items are user-actionable:
a fully offline run and a manual UI click-through — both documented above.
**Next module:** Module 6 is not yet defined in `docs/mvp-requirements.md`;
the natural next step is the “Ask RecallAI” retrieval/Q&A surface (placeholder
`src/pages/AskRecallAI.tsx` exists), pending the user's module plan.
No commit or push has been made; the working tree holds all Module 3–5 work
uncommitted.

## Module 6 — RAG and semantic retrieval — ✅ COMPLETE (2026-10-12)

### Tasks 6.1–6.3 — DONE (prior sessions, re-verified 2026-10-12)

- **6.1 chunking:** deterministic sentence-aware chunker
  (`backend/app/services/chunking.py`, defaults 1200 chars / 150 overlap),
  stable `chk_` ids, offsets into normalized text, `ChunkRepository`
  (`backend/app/repositories/chunk_store.py`) with idempotent replace and
  lifecycle sync; migration `20261011_0002` (`memory_chunks` + `chunk_fts`
  with insert/update/delete triggers). Tests: `test_chunking.py` (12),
  `test_chunk_index.py` (7).
- **6.2 embeddings:** local `nomic-embed-text` (768 dims, ~274 MB, verified
  live via Ollama `/api/embed`) through `EmbeddingService`
  (`backend/app/services/embeddings.py`) — same loopback-only, injectable-
  transport contract as the Module 5 summarizer; single/batch/query paths
  share one model. Config: `RECALLAI_EMBEDDING_MODEL`,
  `RECALLAI_EMBEDDING_TIMEOUT_SECONDS`, `RECALLAI_MAX_EMBEDDING_INPUT_CHARS`.
  Tests: `test_embeddings.py` (23), all mocked.
- **6.3 vector index:** SQLite `chunk_embeddings` table (float32 blobs +
  model/dims per row; migration `20261011_0003`), pure-Python cosine scan
  (`backend/app/services/vectors.py`, no NumPy — documented O(n·d) MVP
  limit behind the replaceable `VectorStore` interface in
  `backend/app/repositories/vector_store.py`), stale-generation detection,
  FK-cascade deletion. Tests: `test_vector_store.py` (15).
- Retrieval config added alongside (commented, env-overridable):
  `RECALLAI_RAG_CANDIDATES` (20), `RECALLAI_RAG_TOP_K` (6),
  `RECALLAI_RAG_MIN_SIMILARITY` (0.25), `RECALLAI_RAG_SEMANTIC_WEIGHT` /
  `RECALLAI_RAG_KEYWORD_WEIGHT` (1.0), `RECALLAI_RAG_RRF_K` (60),
  `RECALLAI_RAG_EVIDENCE_BUDGET_CHARS` (6000),
  `RECALLAI_RAG_MAX_QUESTION_CHARS` (1000).

### Task 6.4 — Semantic retrieval service — DONE (2026-10-12)

- `backend/app/services/temporal.py`: query validation (non-empty,
  1000-char limit, meaning never rewritten) + temporal parsing for
  "yesterday" (single prior day), "last week" (prior Mon–Sun ISO week),
  and "<in|from|during|for> <Month>" (whole calendar month; a month still
  ahead this year means last year). All bounds inclusive `[from, to]`,
  matched against `captured_at` in UTC, consistent with the memories list
  API (`_day_bounds_utc`). Only recognized patterns produce filters;
  anything ambiguous ("recently", "last summer") returns None. Specificity
  order: yesterday > last week > month. `now` is injected for
  deterministic tests. Tests: `test_temporal.py` (19).
- `backend/app/services/retrieval.py`: `SemanticRetrievalService` —
  validate → parse temporal → embed question locally (same model as
  documents) → cosine search (active generation only, similarity floor
  0.25) → join each hit to chunk+memory+source rows → apply date window
  (explicit caller dates win; parsed expression still reported) → ranked
  `Evidence` (chunk/memory/source ids, passage, title, URL, domain,
  captured_at, similarity). Deleted memories can never appear (cascade +
  assembly join requires the memory row; orphans skipped). Failures map to
  `RetrievalInputError` / `RetrievalUnavailableError`. Tests:
  `test_retrieval.py` (19), fully mocked, fixed NOW=2026-10-12.
- Verification: backend suite **227 passed, 0 failed** (189 baseline + 38
  new: 19 temporal + 19 retrieval). `git diff --check` clean. Nothing
  staged/committed/pushed.

### Task 6.5 — Hybrid retrieval with RRF ranking — DONE (2026-10-12)

- `backend/app/services/keyword_search.py`: `KeywordSearchService`
  over the `chunk_fts` virtual table (FTS5 with substring fallback),
  rank-ordered. Tests: `test_keyword_search.py` (20).
- `backend/app/services/hybrid.py`: `HybridRetrievalService` fuses the
  semantic and keyword ranked lists with **Reciprocal Rank Fusion** —
  `score = w_sem/(k + rank_sem) + w_kw/(k + rank_kw)`, `k` default 60,
  weights from `RECALLAI_RAG_SEMANTIC_WEIGHT` /
  `RECALLAI_RAG_KEYWORD_WEIGHT`. Semantic candidates come from the real
  `SemanticRetrievalService` path (embedding, cosine floor, date window,
  deletion join), keyword candidates from FTS; results carry `score`,
  `keyword_rank`, and `matched_by` per item. Tests:
  `test_hybrid_retrieval.py` (29, including 3 explicit-date-filter
  tests added when the date-filter defect was fixed — see the Module 6
  verification pass below).
- Verification: full backend suite green.
  Nothing staged/committed/pushed.

### Task 6.6 — Ask RecallAI API endpoint — DONE (2026-10-12)

- `backend/app/api/routes/retrieval.py` (included from `app.main`):
  `POST /api/v1/ask` retrieves grounded evidence via the hybrid service
  (dependency `get_retrieval_service` in `app/api/deps.py` so tests can
  substitute the boundary), `POST /api/v1/memories/{id}/index` builds the
  retrieval index for one memory (404 when absent, 503 when the local
  embedding model is down), and `POST /api/v1/index` backfills memories
  that have chunks but no vectors. Indexing is explicit and
  user-initiated, never automatic on save.
- Response contract: `AskResponse` (`app/schemas/retrieval.py`) with
  verbatim question, ranked `EvidenceItem`s (chunk/memory/source ids,
  passage, title, URL, domain, captured_at, similarity, keyword_rank,
  fused score, `matched_by` channels, confidence), overall `confidence`,
  contributing `channels`, `candidates_considered`, parsed
  `temporal_expression`/`temporal_from`/`temporal_to`, and `request_id`.
  Evidence only — the endpoint never generates an answer.
- Error mapping to the shared envelope: 422 `VALIDATION_ERROR`
  (empty/oversized question, service input error), 503
  `PROVIDER_NOT_CONFIGURED` (embedding model unreachable/outage, with the
  internal message never leaked), 404 `NOT_FOUND` (index endpoint).
  `X-Request-ID` echoed.
- Privacy: the question text is never logged (only its length, evidence
  count, confidence, and channels); no credentials are accepted (a stray
  `api_key` body field is ignored); deleted memories cannot appear
  (cascade deletion + assembly join requires the memory row).
- Tests: `test_retrieval_api.py` (18) with a fake embedding transport
  and dependency overrides (3 of them covering the explicit
  `from_date`/`to_date` pass-through added when the date-filter defect
  was fixed — see the Module 6 verification pass below);
  `test_retrieval_pipeline.py` (4) end-to-end through a temporary
  database.
- Verification: backend suite green. Nothing staged/committed/pushed.

### Tasks 6.7 & 6.8 — Evidence assembly, confidence, and grounded prompt — DONE (2026-10-12)

- `backend/app/services/evidence.py` (shared by 6.4–6.6): the grounded
  `Evidence` record, `assemble_evidence()` (the deletion guarantee —
  requires chunk row AND memory row, skips orphans), `effective_window()`
  (explicit caller dates win over a parsed expression; the parsed window
  is still reported), `in_window()` (inclusive day-granular UTC bounds),
  and `fuse_rankings()` (the RRF implementation used by Task 6.5).
  Re-exports `normalize_and_parse` / `TemporalFilter` from `temporal.py`
  so callers have one import.
- `backend/app/services/prompt.py` (Task 6.7 confidence + Task 6.8
  prompt):
  * `assess_confidence()` → `none` (no matches), `strong`
    (≥ `rag_min_evidence_for_strong` passages all at/above
    `rag_confidence_strong`, and not keyword-only), `weak` otherwise —
    thresholds configurable through `Settings`. A BM25-only hit can
    never be strong (no semantic corroboration).
  * `build_prompt(question, evidence, settings)` → empty string when
    there is no evidence; otherwise a QUESTION block followed by
    `BEGIN EVIDENCE (untrusted data)` … `--- END EVIDENCE ---` with
    numbered `[n] memory_id=… chunk_id=…` citations, whole passages
    only (never mid-passage truncation), highest-ranked kept first,
    bounded by `rag_evidence_budget_chars`, and instructions to cite
    evidence and say so plainly when the evidence does not answer.
  * Tests: `test_prompt_confidence.py` (16).
- Verification: backend suite green. Nothing staged/committed/pushed.

### Task 6.9 — Frontend integration (real API, not mocks) — DONE (2026-10-12)

- `src/lib/memoriesApi.ts`: real API client for Module 6 —
  `askRecallAi()` → `POST /ask`, `indexMemory()` →
  `POST /memories/{id}/index`, with `AskResult` / `AskEvidence` /
  `AskRequest` / `RetrievalConfidence` types mirroring the backend
  `AskResponse` / `EvidenceItem` schemas. Uses the same `apiBase`
  (Vite `VITE_API_BASE_URL`, default `http://127.0.0.1:8000/api/v1`) and
  the shared error-envelope reader used by the Module 4/5 clients —
  no mocked responses anywhere on this path.
- `src/pages/AskRecallAI.tsx`: four distinct states (loading / error
  with retry / empty with “no evidence ≠ error” explanation / results
  as numbered `EvidenceCard`s showing passage, source title, domain,
  captured time, similarity %, keyword rank, matched channels, and a
  link to the full memory). Confidence badge (none/weak/strong),
  multi-turn conversation, suggested questions, AbortSignal on each
  request, and an explicit “retrieves evidence, does not generate
  answers” disclaimer.
- `src/pages/CompanionSidePanel.tsx`: same `askRecallAi()` client for
  contextual questions, with source references per turn.
- Tests: `src/test/AskRecallAI.test.tsx` (8) covering empty→results flow,
  real evidence metadata rendering, empty state, error + retry,
  confidence badges, and abort behavior. Frontend suite **59 passed**
  (12 files, including extension tests).
- Verification: `npm test -- --run` → 59 passed. Nothing
  staged/committed/pushed.

### Task 6.10 — Retrieval evaluation dataset and metrics — DONE (2026-10-12)

- `backend/app/services/evaluation.py`: deterministic synthetic corpus
  (6 memories across vector-db / cooking / privacy / local-embeddings /
  withdrawn topics, 5-dim topic vectors, fixed reference day
  `2026-10-12`) plus 10 evaluation cases covering every required kind:
  exact-match, paraphrase, temporal (in-window and out-of-window),
  source-filtered (positive and negative), irrelevant, duplicate,
  deleted-memory, and missing-metadata.
- Metrics: `recall_at_k`, `precision_at_k`, `reciprocal_rank` per case;
  `EvaluationReport` aggregates mean Recall@k / Precision@k / MRR,
  per-kind breakdown, pass/fail; `format_report()` renders a
  human-readable summary. `evaluate()` scores with the **same rules as
  production** — production `cosine_similarity`, the 0.25 similarity
  floor, real `parse_temporal`, source-type filtering, deleted memories
  removed before scoring, deterministic tie-break on memory id. Deleted
  memories are excluded by construction, so a deleted-memory hit is
  measured (fails) rather than merely asserted.
- Tests: `test_evaluation.py` (21).
- Verification: backend suite green. Nothing staged/committed/pushed.

### Module 6 verification pass (2026-10-12, this session)

- **Re-verified end to end rather than trusting prior notes.** The
  earlier session's ledger stopped at Task 6.4 even though 6.5–6.10
  were implemented and tested; this session audited every component,
  closed the ledger gap, and re-ran everything.
- Backend: `.venv/bin/python -m pytest` → **344 passed, 0 failed**
  (28 test modules; Module 6 adds 160: chunking 12, chunk index 7,
  embeddings 23, vector store 15, temporal 19, retrieval 19, keyword
  search 20, hybrid 29, prompt/confidence 16, retrieval API 18,
  retrieval pipeline 4, evaluation 21, indexing 9). One pre-existing
  `python-multipart` deprecation warning only.
- Frontend: `npm test -- --run` → **59 passed, 0 failed** (12 files).
- Retrieval endpoint confirmed present and wired:
  `backend/app/api/routes/retrieval.py` (`POST /api/v1/ask`, plus the
  two indexing routes) is included by `app.main`, uses the shared
  dependency/error-envelope/request-id conventions, and is exercised
  by `test_retrieval_api.py` against the real hybrid service with a
  fake embedding transport.
- Frontend confirmed wired to the real backend: `askRecallAi()` in
  `src/lib/memoriesApi.ts` calls `POST /ask` over the shared
  `apiBase` — no mock layer on this path; `AskRecallAI.tsx` and
  `CompanionSidePanel.tsx` both consume it.
- One code cleanup: removed two unreachable trailing lines
  (`return corpus, cases` sitting at module level after
  `format_report` in `evaluation.py` — dead code from a misplaced
  indent; `build_dataset()` already returns correctly at line ~329).
- **Defect found and fixed — explicit date filters were accepted but
  ignored.** The `AskRequest` schema exposed optional `from_date` /
  `to_date` fields, but the route never passed them and
  `HybridRetrievalService.retrieve()` had no date parameters — a client
  could send a range and silently get unfiltered results (the schema
  promised filtering that did not happen). Fixed by wiring them through:
  * `AskRequest.from_date`/`to_date` changed from `datetime` to
    day-granular `date` (inclusive UTC calendar days, matching the
    memories list API convention and `effective_window`'s signature;
    Pydantic rejects datetime-typed strings so clients cannot send a
    time-of-day that would be silently truncated).
  * Route `ask()` now passes `request.from_date`/`request.to_date` to
    `service.retrieve()`.
  * `HybridRetrievalService.retrieve()` gained optional `from_date`/
    `to_date` parameters and now uses the already-imported (previously
    dead) `effective_window()` helper: an explicit caller range wins
    over the parsed expression, the parsed expression is still reported
    for transparency, an inverted range raises `RetrievalInputError`
    (→ 422, same rule as the memories list API), and the resulting
    window applies to **both** the semantic and keyword channels plus
    the final evidence join — consistent with the module's stated
    filtering guarantee.
  * `src/lib/memoriesApi.ts` `AskRequest` type updated with optional
    `from_date`/`to_date` for parity (UI does not yet expose date
    pickers on the Ask screen; the fields are API-level).
  * New tests (6): API-level — explicit dates reach the service, absent
    dates pass `None`, inverted range → 422 `VALIDATION_ERROR`;
    service-level — explicit range overrides "last week" while the
    parsed expression stays reported, keyword-only results obey the same
    window, inverted range raises `RetrievalInputError`.
- Re-verified after all edits: backend **344 passed, 0 failed**
  (338 + 6 new); frontend **59 passed** (12 files);
  `npx tsc -b --noEmit` exit 0; `npm run lint` clean.
- Nothing staged/committed/pushed; all Module 6 work remains local
  uncommitted history awaiting user review.

