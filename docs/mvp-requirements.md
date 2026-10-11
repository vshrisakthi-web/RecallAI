# RecallAI — MVP Requirements

**Module 1, Task 1.1 — Define MVP Requirements**

> **Status legend**
>
> - 🟡 **Planned** — Intended for the MVP but not yet built.
> - 🟢 **Implemented** — Built and working.
>
> **Current implementation status:** 🟡 **Nothing is implemented yet.**
> As of this document, the repository contains only a `README.md` title and this
> requirements file. No application code, components, packages, or configuration
> exist. Every requirement listed below is therefore marked 🟡 **Planned**.
>
> This list will be updated (moving items from 🟡 to 🟢) as each task is completed.

---

## 1. Product Vision

RecallAI is a **privacy-first personal AI memory assistant**. Its purpose is to
help individuals capture, organize, and recall information they encounter across
the web — without surrendering their personal data to third parties.

The guiding principle is **"your memory stays yours."** Unlike tools that upload
browsing content to remote servers for processing, RecallAI is designed so that
sensitive data remains under the user's control. AI-assisted features (such as
summarizing or recalling saved items) must respect that boundary.

RecallAI should feel like a trusted second brain: lightweight, fast, respectful
of privacy, and genuinely useful for everyday recall.

---

## 2. Target Users

The MVP focuses on a single primary persona:

- **The privacy-conscious knowledge worker / student.**
  Someone who saves articles, notes, links, and snippets across many tabs and
  tools, and who wants a single place to recall them later — but who is
  uncomfortable with cloud services that mine or transmit their data.

Secondary (future) audiences, noted but **out of scope for the MVP**:

- Researchers managing large personal corpora.
- Teams (would require shared/remote storage — deferred).

---

## 3. Problem Statement

People constantly encounter information they want to remember — articles,
product pages, code snippets, meeting notes — and save it across scattered tools
(browser bookmarks, notes apps, chat messages). This leads to:

- **Fragmentation:** Saved items live in many disconnected places.
- **Poor recall:** Once saved, items are hard to find again, often because there
  is no searchable memory or context.
- **Privacy risk:** Most "AI assistant" tools send this personal content to
  remote servers to process, exposing private data to third parties and creating
  compliance and trust concerns.

The core tension users face: they want **intelligent recall** but not at the
cost of **giving up their privacy**.

---

## 4. MVP Goals

The MVP aims to prove the core value loop with minimal scope:

1. **Capture** — Let the user save a memory item (text, link, or note) quickly
   from within the browser.
2. **Store locally** — Persist captured items on the user's own device, with no
   data leaving it by default.
3. **Recall / browse** — Let the user view, search, and revisit their saved
   memories through a simple interface.
4. **Demonstrate privacy-first design** — Show that the app works end-to-end
   using local data and mock/offline AI behavior, with clear boundaries that no
   personal data is transmitted externally.

**Non-goals for the MVP:** full natural-language AI, cross-device sync,
collaboration, and any server-side infrastructure.

---

## 5. Surfaces / Components (Planned)

The MVP spans three user-facing surfaces. For the initial frontend, **all three
use React + TypeScript with mock data** (see Section 7).

### 5.1 Chrome Extension Popup  🟡 Planned

The quick-capture and quick-recall entry point opened from the browser toolbar.

Intended capabilities:

- Quick "save current page" action (capture title + URL).
- A small text field for quick notes.
- A short list of recently saved memories (mock data initially).
- A basic search box to filter the local list.
- Clear indicator that data is stored **locally** on the device.

### 5.2 Companion Side Panel  🟡 Planned

A persistent panel that lives alongside the page for richer interaction.

Intended capabilities:

- Displays the user's saved memories in a scrollable, searchable list.
- Shows details of a selected memory (content, source link, timestamp).
- Placeholder area for future AI-assisted features (e.g., "summarize this"),
  which will use mock responses in the MVP.
- Reinforces the local-first, privacy-preserving model.

### 5.3 Web Dashboard  🟡 Planned

The full-screen management interface, the MVP's primary "home base."

Intended capabilities:

- Full list/grid view of all saved memories.
- Search and basic filtering (e.g., by date or tag).
- Detail view for an individual memory.
- Add / edit / delete memory items (operating on local/mock data).
- A "Privacy" indicator summarizing the local-first, no-upload stance.

---

## 6. Privacy Requirements  🟡 Planned

Privacy is the defining constraint of the product. The MVP must:

- **Store all personal memory data locally** on the user's device (e.g., via
  browser local storage / IndexedDB) by default.
- **Transmit no personal content to external servers.** Any network calls, if
  present at all, must exclude user memory content.
- **Use mock / offline AI behavior** for the MVP. No real AI API calls that would
  send user data off-device.
- **Be transparent:** clearly communicate to the user where their data lives and
  that it is not uploaded.
- **Avoid third-party analytics or trackers** that could leak usage or content
  data.

> These are the requirements the implementation will be measured against as
> tasks progress; none are implemented yet.

---

## 7. Technical Boundaries  🟡 Planned

Constraints that shape how the MVP is built:

- **Frontend stack:** **React + TypeScript** for the initial frontend, using
  **mock data** in place of a real backend.
- **Mock data only:** No live backend, database server, or external API is
  required for the MVP. Data will be seeded from local mock/static sources so the
  UI can be built and demonstrated independently.
- **Local persistence (planned):** Browser-based storage (e.g., IndexedDB or
  `localStorage`) is the intended home for real user data once persistence is
  implemented; this is not yet built.
- **Chrome extension packaging (planned):** The popup and side panel are intended
  to run as a Manifest V3 Chrome extension; the web dashboard is a standalone web
  page. Extension scaffolding is not yet set up.
- **No external AI services in the MVP.** AI features are simulated with mock
  responses to preserve privacy.
- **TypeScript throughout:** Type safety is required from the start.


---

## 8. Out-of-Scope Features  🟡 Planned

Explicitly **not** part of the MVP (documented to prevent scope creep):

- Real AI / LLM integration or any cloud AI API calls.
- Cross-device synchronization or cloud backup.
- User accounts, authentication, and multi-user support.
- Team / shared workspaces or collaboration.
- Mobile apps (iOS / Android).
- Browser support beyond Chrome for the MVP.
- Data import/export from other tools (e.g., importing bookmarks).
- Offline AI models running locally (future consideration, not MVP).
- Monetization, billing, or subscription features.
- Analytics dashboards or usage tracking.

---

## 9. Success Criteria  🟡 Planned

The MVP is considered successful when:

1. A user can **capture** a memory item and see it appear in the interface.
2. A user can **search** and **retrieve** a saved memory from the local/mock
   store.
3. All three surfaces (popup, side panel, web dashboard) render functional
   screens built with **React + TypeScript** and **mock data**.
4. The app demonstrably works **without sending any personal data off-device**
   (verified via the local-only data flow and mock AI behavior).
5. The codebase is **TypeScript** and compiles/type-checks cleanly.

These criteria describe the target state; **none are met yet** because no
application code has been written.

---

## 10. Implementation Status Summary

| Requirement area            | Status         | Notes                                              |
| --------------------------- | -------------- | -------------------------------------------------- |
| Repository / Git init       | 🟢 Implemented | Git repository initialized.                        |
| README title                | 🟢 Implemented | `README.md` contains only the `# RecallAI` title.  |
| MVP requirements (this doc) | 🟢 Implemented | This document.                                     |
| `docs/` directory           | 🟢 Implemented | Created as part of this task.                      |
| Product vision              | 🟢 Implemented | Documented above.                                  |
| Chrome extension popup      | 🟡 Planned     | Not started.                                       |
| Companion side panel        | 🟡 Planned     | Not started.                                       |
| Web dashboard               | 🟡 Planned     | Not started.                                       |
| React + TypeScript frontend | 🟡 Planned     | Not scaffolded; no packages installed yet.         |
| Mock data layer             | 🟡 Planned     | Not created.                                       |
| Local persistence           | 🟡 Planned     | Not implemented.                                   |
| Privacy safeguards in code  | 🟡 Planned     | Requirements defined; no code yet.                 |

**Note on status:** The only items marked 🟢 Implemented are the documentation and
Git scaffolding created so far. All application functionality remains 🟡 Planned.

