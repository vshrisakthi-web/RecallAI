# RecallAI — Interface Specification

**Module 1, Task 1.2 — Define the three interfaces**

> **Purpose:** Define the purpose, primary actions, content, states, navigation, and
> responsibilities of the three RecallAI surfaces, and clarify which surface owns
> each responsibility to avoid duplication.
>
> **Source of truth:** `docs/mvp-requirements.md` (vision, MVP scope, privacy) and
> `docs/PROJECT_CONTEXT.md` (technology decisions).
>
> **Status:** 🟢 **Specified** (documented). Implementation is 🟡 **not started** —
> no React components exist yet. This document is the blueprint that Tasks 1.3–1.9
> will build against.
>
> **Legend:** 🟡 Planned / not built · 🟢 Documented & agreed.

---

## 0. Shared concepts and vocabulary

These terms are used consistently across all three interfaces. Defining them once
avoids each screen inventing its own wording.

- **Memory** — a single saved item (text note, link/page, or snippet) with a title,
  content, source URL (when available), capture date, and optional tags/source type.
- **Capture** — the act of saving a memory. "Capture" is the product's core verb.
- **Capture state** — one of `active`, `paused`, `stopped`. (Introduced in Task 1.2;
  modeled in the data layer in Task 1.9.)
- **Source reference / citation** — the origin of a memory (URL and/or source type)
  shown so the user can trust and revisit it.
- **Ask RecallAI** — the question-and-answer surface where the user asks questions
  and receives answers **with source references**. In the MVP, answers are **mock**
  (see §5.3) and must be visibly labelled as such.
- **Mock vs. real** — any AI output shown before a real backend exists must be
  clearly marked "Mock". No fake live-AI claims.

### Guiding principles (apply to every surface)

1. **Privacy-first, local-only:** every screen communicates that data is stored
   locally and nothing is uploaded. A small, consistent **privacy indicator** is
   available app-wide.
2. **One owner per responsibility:** each capability lives in exactly one primary
   surface (see §6 ownership matrix) to avoid duplicated logic and confusing UX.
3. **Consistent visual language:** shared navigation, colors, spacing, and state
   treatments (loading / empty / error / populated) so the three surfaces feel like
   one product.
4. **No invented functionality:** mock data and mock answers are clearly labelled;
   nothing implies a working AI backend or granted permissions that don't exist.


---

## 1. Interface A — Chrome Extension Popup

**Purpose:** A small, fast toolbar popup for **quick capture control and at-a-glance
recall** without leaving the current page. It is the lightweight "control center,"
not the place for deep browsing.

**Runtime (planned):** Manifest V3 Chrome extension popup. 🟡 Not built.

### Primary actions
- **Start / Pause / Stop capture** — control the capture state. Only the valid
  action(s) for the current state are shown (see states below).
- **Capture current page** — save the active tab as a memory (title + URL).
- **Open companion side panel** — hand off to the richer surface.
- **Open settings / Privacy Settings** — jump to privacy controls (dashboard owns
  the full screen; the popup can deep-link).
- **Search** — quick filter of the recent-memories list shown in the popup.

### Content shown
- **Capture status** — current state label (`Active` / `Paused` / `Stopped`) with a
  clear, accessible status indicator (icon + text + color).
- **Current website information** — the active tab's title and domain, so the user
  knows what "capture" would save.
- **Recent capture / memory summary** — a short list (most recent first) of recent
  memories; tapping one navigates to its detail view.
- **Privacy indicator** — confirms data is stored locally.

### States
| State    | Shown controls        | Meaning                                   |
| -------- | --------------------- | ----------------------------------------- |
| `active` | Pause, Stop           | Capture is running.                       |
| `paused` | Resume, Stop          | Capture is temporarily suspended.         |
| `stopped`| Start capture         | Capture is inactive.                      |

Plus common UI states for the recent list: **loading**, **empty** ("no memories
yet"), **error** (failed to load).

### Navigation
- → Companion side panel (open panel).
- → Privacy Settings (deep link into dashboard).
- → Memory Detail (from a recent-memory item).

### Ownership / responsibility
- **Owns:** capture-state control and current-page context (the quickest place to
  start/pause/stop and capture the current tab).
- **Does not own:** full memory browsing, editing, or the Ask RecallAI experience —
  those belong to the dashboard / side panel. The popup shows only a *summary* and
  links out.

---

## 2. Interface B — Companion Side Panel

**Purpose:** A **persistent panel** docked beside the page for contextual,
conversational recall — asking questions about the current page and seeing related
memories while browsing.

**Runtime (planned):** Manifest V3 Chrome extension side panel. 🟡 Not built.

### Primary actions
- **Ask a contextual question** — type a question; receive an answer with source
  references (mock in the MVP).
- **View conversation history** — scroll through prior Q&A in the session.
- **Open a source / related memory** — jump to a cited memory or its detail view.
- **See current-page context vs. stored memories** — clearly separated.
- **Start capture** (optional control) — a convenience control mirroring the popup.

### Content shown
- **Current page context** — a clearly labelled section describing the active page
  (title/domain), distinct from stored memories.
- **Conversation history** — prior questions and answers in the session.
- **Responses with source references** — each answer lists the memories/URLs it drew
  from; **mock answers are visibly labelled "Mock".**
- **Related memories** — memories relevant to the current page/question.

### States
- **Loading** — while a (mock) answer is "being generated."
- **Empty** — no conversation yet (prompt + suggested questions shown).
- **Error** — the request failed (retry offered).
- **Populated** — conversation present.

### Navigation
- → Memory Detail (from a source reference or related memory).
- → Ask RecallAI (dashboard) for the full-screen Q&A experience.

### Ownership / responsibility
- **Owns:** the **contextual, conversational** experience tied to the current page.
- **Does not own:** bulk memory management or global settings — those belong to the
  dashboard. The panel focuses on "ask about what I'm looking at right now."

---

## 3. Interface C — Web Dashboard

**Purpose:** The full-screen **management home base** for the user's memory. It owns
the authoritative, complete experience: browsing everything, editing, asking
questions, and controlling privacy.

**Runtime (planned):** Standalone web page (React + TypeScript, routed). 🟡 Not built.

The dashboard has **five screens**. A persistent app shell provides consistent
navigation between them (sidebar or top nav), plus the app-wide **privacy indicator**
and **capture-status** summary.

### 3.1 Overview (landing screen)

- **Purpose:** At-a-glance home: what's been captured and where to go next.
- **Content:** memory activity summary (counts / recent activity), recent memories
  list, search entry point, quick link to Ask RecallAI, capture status, and
  source + privacy indicators.
- **States:** loading, empty (first-run welcome), populated.

### 3.2 Memory Timeline

- **Purpose:** Browse all memories chronologically.
- **Content:** chronological memory cards, search box, filters (by source type and
  date), memory previews. Clicking a card opens **Memory Detail**.
- **States:** loading, empty (no memories), **no-search-matches**, error, populated.

### 3.3 Ask RecallAI

- **Purpose:** Full-screen question-and-answer over the user's memories.
- **Content:** chat history, question input, suggested questions, answer cards with
  **source citations/references**. Answers are **mock** in the MVP and must be
  **visibly labelled "Mock answer"** — distinct from any future real AI output.
- **States:** loading (generating), empty (no questions yet), error (failed),
  populated. No fake live-AI backend is implemented.

### 3.4 Memory Detail

- **Purpose:** Inspect and manage a single memory.
- **Content:** title, content, original source + source link (when available),
  capture date, relevant metadata (source type, tags), **delete action**, and a way
  to **return to the Memory Timeline**.
- **States:** loading, populated, error (not found / failed to load).

### 3.5 Privacy Settings

- **Purpose:** Give the user transparent control and clear privacy explanations.
- **Content:** capture preferences, capture status & controls (start/pause/stop),
  excluded / sensitive-page handling, memory deletion controls, and **plain-language
  explanations of each privacy implication**.
- **Guardrail:** Must not imply unrestricted browser monitoring or claim permissions

---

## 4. Responsibility ownership matrix (avoid duplication)

| Responsibility                     | Popup | Side Panel | Dashboard | Notes |
| --------------------------------- | :---: | :--------: | :-------: | ----- |
| Start / Pause / Stop capture      |  ✅   |     ○      |    ✅     | Popup = fastest control; dashboard = full controls in Privacy Settings. |
| Capture current page              |  ✅   |     ○      |    ✗      | Popup owns the in-browser quick capture. |
| Current-page context              |  ✅   |     ✅     |    ✗      | Popup (summary) + side panel (deep context). |
| Browse all memories               |  ✗   |     ○      |    ✅     | Dashboard is authoritative. |
| Search memories                   |  ○   |     ○      |    ✅     | Full search/filters live in the dashboard. |
| Edit / delete a memory            |  ✗   |     ✗      |    ✅     | Only the dashboard mutates memory records. |
| View Memory Detail                |  ○   |     ○      |    ✅     | Detail screen is owned by the dashboard; others link to it. |
| Ask RecallAI (full Q&A)           |  ✗   |     ✅     |    ✅     | Side panel = contextual; dashboard = full-screen. |
| Contextual Q&A about current page |  ✗   |     ✅     |    ✗      | Side panel's specialty. |
| Privacy Settings (full controls)  |  ○   |     ✗      |    ✅     | Dashboard owns settings; popup may deep-link. |

Legend: ✅ primary owner · ○ secondary/link · ✗ not offered here.

**Why this matters:** each capability has exactly one **primary owner** so logic and
data aren't duplicated across surfaces. Other surfaces either link to the owner or
show a read-only summary.

---

## 5. Shared states, navigation, and consistency

- **Global UI states** every list/screen must handle: **loading**, **empty**,
  **error**, **populated**; the Timeline and search also handle **no-search-matches**.
- **Capture state** (`active` / `paused` / `stopped`) is shared vocabulary; the popup
  controls it, and the dashboard/side panel reflect it.
- **Navigation is deep-linkable within the dashboard** (routes per screen); the
  popup and side panel open dashboard screens where a full experience is needed.
- **Privacy indicator** and **mock labelling** are consistent across all surfaces.

---

## 6. Out of scope for this specification

Per `mvp-requirements.md` §8, this spec does **not** define: real AI/LLM behavior,
cloud sync, accounts/auth, teams, mobile, non-Chrome browsers, data import/export,
offline AI models, monetization, or analytics. The "Ask RecallAI" and side-panel
answers are **mock-only** for the MVP.

---

## 7. Implementation status

| Interface / screen            | Specified | Implemented |
| ---------------------------- | :-------: | :---------: |
| A. Chrome extension popup    |    🟢     |     🟡      |
| B. Companion side panel      |    🟢     |     🟡      |
| C. Web Dashboard (shell)     |    🟢     |     🟡      |
|   — Overview                 |    🟢     |     🟡      |
|   — Memory Timeline          |    🟢     |     🟡      |
|   — Ask RecallAI             |    🟢     |     🟡      |
|   — Memory Detail            |    🟢     |     🟡      |
|   — Privacy Settings         |    🟢     |     🟡      |

**Next step:** Tasks 1.3–1.8 will turn these screens into Google Stitch design
prompts; Task 1.9 will implement the UI against this specification using mock data.

  that have not been granted.
- **States:** default (populated controls), plus inline confirmations for
  destructive actions (e.g., delete).

### Dashboard navigation map

```
Overview ──┬──> Memory Timeline ──> Memory Detail ──(back)──> Memory Timeline
           ├──> Ask RecallAI
           └──> Privacy Settings
```
Every screen is reachable from the app shell; Memory Detail returns to the Timeline.

### Ownership / responsibility
- **Owns:** the complete memory model — browsing all memories, editing/deleting, the
  full Ask RecallAI experience, and all privacy/settings controls. It is the single
  source of truth for management actions.
- **Does not own:** quick, in-context capture control and current-page context
  (those are the popup's and side panel's strengths). The dashboard *summarizes*
  capture status but the popup is the fastest place to change it.

