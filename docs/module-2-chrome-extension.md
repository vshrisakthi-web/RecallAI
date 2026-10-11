# RecallAI — Module 2: Chrome Extension & Capture Engine

This module turns the approved Module 1 UI into a **working Chrome Manifest V3
extension** that captures useful, permitted page content on an explicit user
action, stores it locally, and exposes Active / Paused / Stopped states. It has
**no production AI, no backend, and no automatic surveillance** — capture is
always user-triggered, and nothing is uploaded by default.

## Architecture

```
popup (React UI)
   │  typed messages (chrome.runtime.sendMessage)
   ▼
background service worker  ── coordinates, guards state, builds records
   │  chrome.scripting.executeScript (on demand, activeTab)
   ▼
content script (injected only after Capture) ── reads permitted page text
   │  structured extraction result
   ▼
CaptureRepository  ── chrome.storage.local  (records + capture state)
   │  optional, disabled-by-default
   ▼
local backend adapter (localhost only, non-fatal)
```

**Data flow for one capture:** user clicks Capture → popup sends `CAPTURE`
(with the active tab + capture type) → worker checks the capture state, rejects
if Paused/Stopped, rejects restricted pages, injects the content script, gets an
extraction, builds a `CaptureRecord`, saves it to `chrome.storage.local`, and
returns a summary. The optional backend sync only runs if a localhost endpoint
is explicitly configured, and its failure never blocks the capture.

## Folder structure

```
extension/
├─ manifest.json            # MV3 manifest (minimal permissions)
├─ assets/                  # generated icons (16/48/128) — npm run icons:extension
├─ types/index.ts           # CaptureRecord, ExtractionResult, TabInfo, CaptureState
├─ lib/
│  ├─ messages.ts           # typed request/response unions + isValidMessage guard
│  ├─ state.ts              # capture state machine + allowed transitions
│  ├─ domain.ts             # URL → domain, restricted-page + YouTube detection
│  ├─ limits.ts             # MAX_TEXT_LENGTH (text-size cap)
│  ├─ extract.ts            # readable-text + selection extraction (DOM heuristics)
│  ├─ capture.ts            # buildRecord: extraction → CaptureRecord
│  ├─ storage.ts            # CaptureRepository over chrome.storage.local
│  └─ backend.ts            # optional localhost adapter (disabled by default)
├─ content/contentScript.ts # injected on demand; EXTRACT / EXTRACT_SELECTION
├─ background/serviceWorker.ts  # message router + capture orchestration
├─ popup/                   # React popup (Popup.tsx, index.tsx, popup.html/.css)
├─ tests/                   # unit tests + HTML fixtures
└─ scripts/                 # gen-icons.mjs, assemble.mjs, verify-dist.mjs
```

## Manifest permissions and rationale

| Permission | Why it's the minimum |
|------------|----------------------|
| `activeTab` | Temporary access to the current tab **only after** the user invokes the extension. No persistent all-sites access. |
| `scripting` | To inject the content script into the active tab on demand. |
| `storage` | To persist capture records and state in `chrome.storage.local`. |
| `host_permissions` | **Intentionally empty.** We never request broad URL access. |

CSP for extension pages is locked to `script-src 'self'; object-src 'self'` — no
remote code. `minimum_chrome_version` is 102.

## Data model

`CaptureRecord` (see `extension/types/index.ts`):

- `id` — stable unique id (`mem_<timestamp>_<rand>`)
- `title` — page title (falls back to domain)
- `url`, `domain`
- `capturedAt` — ISO timestamp
- `captureType` — `'full-page'` | `'selection'`
- `extractedText` — the captured text (selection text when applicable)
- `selectedText`, `surroundingContext` — only for selection captures
- `status` — `'ok' | 'empty' | 'partial' | 'error'` (honest extraction status)
- `note` — human-readable caveats (e.g. YouTube transcript not available)
- `contentLength` — character count metadata

We never fabricate `extractedText`; when content is unavailable the record says
so via `status`/`note` rather than inventing text.

## Message contracts

Discriminated unions in `extension/lib/messages.ts`. Popup → background
requests: `GET_STATE`, `SET_STATE`, `GET_ACTIVE_TAB`, `CAPTURE`, `LIST_RECENT`,
`GET_RECORD`, `DELETE_RECORD`. Background → content script: `EXTRACT`,
`EXTRACT_SELECTION`. Every response is an envelope `{ ok: true, data }` or
`{ ok: false, error, code? }`. `isValidMessage` rejects unknown/malformed
messages before they are processed.

## Build commands

```bash
# one-shot: icons → popup → content → background → assemble → verify
npm run build:extension

# individual steps
npm run icons:extension       # write assets/icon{16,48,128}.png
npm run build:ext:app         # popup (React+Tailwind)  -> extension/.stage/popup
npm run build:ext:content     # content script (IIFE)   -> extension/.stage/content
npm run build:ext:background  # service worker (IIFE)   -> extension/.stage/background
node extension/scripts/assemble.mjs   # -> extension/dist-extension (loadable)
node extension/scripts/verify-dist.mjs
```

Output is `extension/dist-extension/` (git-ignored — it is a build artifact).

## Chrome installation (Load unpacked)

1. `npm run build:extension`
2. Open `chrome://extensions`
3. Enable **Developer mode** (top-right)
4. Click **Load unpacked**
5. Select `extension/dist-extension/`
6. Pin the RecallAI icon for easy access

## Manual verification checklist

The capture engine is verified by **unit tests** (build-time). Live browser
behaviour must be checked in Chrome (no browser automation is available here):

- [ ] Open a blog/article page → open popup → **Capture this page** → success
      message + a record appears under "Recent captures".
- [ ] Open a docs page → Capture → headings/paragraphs captured, nav stripped.
- [ ] Select a sentence, tick **Capture only my selected text**, Capture → the
      selected text is saved (type `selection`).
- [ ] Set state to **Paused** → Capture is disabled and shows "Capture is paused".
- [ ] Set state to **Stopped** → Capture is disabled and shows "Capture is stopped".
- [ ] **Resume** (Paused→Active) or **Start** (Stopped→Active) → Capture works again.
- [ ] Close and reopen the popup → the state persists.
- [ ] On a `chrome://` or Web Store page → a clear "restricted by Chrome" message.
- [ ] On a YouTube watch page → a partial record with an explicit note that no
      transcript was captured.

## Known limitations

- **YouTube:** only title/URL and any visible text are captured. Transcripts are
  **not** extracted (no supported, permitted mechanism exists); the record is
  marked `partial` with a note. This is honest by design.
- **No browser-automation test** is wired here; Chrome verification is manual
  (checklist above). Automated tests cover the engine logic.
- **No persistence beyond `chrome.storage.local`** (survives popup close, but
  that is the scope for this module).
- **Backend sync is optional and localhost-only**, disabled by default.
- The popup and the companion side panel share logic but the side panel is still
  previewed in the dashboard (`/panel`); packaging it as a separate Chrome side
  panel (`chrome.sidePanel`) is a possible Module 3 enhancement.

## Backend integration status

No backend exists. `extension/lib/backend.ts` is an **isolated adapter** that,
only when `{ endpoint, enabled: true }` is stored under `recallai.backend` and
the endpoint is localhost, will POST a record. It never uploads by default and
treats failures as non-fatal. No endpoint is invented or assumed.

## Next recommended module

Wire a **local persistence + retrieval layer** the dashboard can read (a shared
bridge from `chrome.storage.local` to the dashboard, or a localhost service the
optional adapter targets), and/or package the companion as a real Chrome side
panel. Backend/Module 3 scope is intentionally undefined here.

