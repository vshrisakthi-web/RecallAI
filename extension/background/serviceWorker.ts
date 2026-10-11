// RecallAI — background service worker (Module 2, Tasks 2.1, 2.3, 2.4, 2.6–2.9)
//
// MV3 service worker that coordinates the capture workflow. It never runs in the
// page and never monitors navigation. It only acts in response to explicit
// popup messages, injects the content script on demand via activeTab+scripting,
// builds a record, and stores it locally. It does NOT auto-capture.

import { buildRecord } from '../lib/capture';
import { DEFAULT_BACKEND_CONFIG, sendToBackend, type BackendConfig } from '../lib/backend';
import { isRestrictedUrl, isYouTubeUrl } from '../lib/domain';
import { isValidMessage, type ContentResponse, type ErrResponse, type Request, type Response } from '../lib/messages';
import { canCapture } from '../lib/state';
import { CaptureRepository, type StorageLike } from '../lib/storage';
import type { CaptureRecord, CaptureState, TabInfo } from '../types';

// --- Storage adapters -------------------------------------------------------

/** Adapt chrome.storage.local to our StorageLike interface. */
const chromeStorage: StorageLike = {
  async get(keys) {
    return chrome.storage.local.get(keys) as unknown as Record<string, unknown>;
  },
  async set(items) {
    await chrome.storage.local.set(items);
  },
  async remove(keys) {
    await chrome.storage.local.remove(keys);
  },
};

const repo = new CaptureRepository(chromeStorage);

/** Load backend config from storage (isolated; disabled unless configured). */
async function loadBackendConfig(): Promise<BackendConfig> {
  const bag = (await chrome.storage.local.get('recallai.backend')) as Record<string, unknown>;
  const raw = bag['recallai.backend'] as Partial<BackendConfig> | undefined;
  if (!raw) return DEFAULT_BACKEND_CONFIG;
  return {
    endpoint: typeof raw.endpoint === 'string' ? raw.endpoint : '',
    enabled: raw.enabled === true,
  };
}

// --- Helpers ----------------------------------------------------------------

function err(error: string, code?: ErrResponse['code']): ErrResponse {
  return code ? { ok: false, error, code } : { ok: false, error };
}

async function getActiveTab(): Promise<chrome.tabs.Tab | null> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab ?? null;
}

function toTabInfo(tab: chrome.tabs.Tab | null): TabInfo | null {
  if (!tab || typeof tab.id !== 'number') return null;
  return { id: tab.id, title: tab.title, url: tab.url };
}

/** Inject the content script (if needed) and request an extraction. */
async function runExtraction(
  tabId: number,
  mode: 'full-page' | 'selection',
): Promise<ContentResponse> {
  try {
    await chrome.scripting.executeScript({ target: { tabId }, files: ['content/contentScript.js'] });
  } catch {
    return {
      ok: false,
      error:
        'Could not access this page. Chrome restricts script injection on some pages ' +
        '(e.g. chrome://, the Chrome Web Store, or the PDF viewer).',
      code: 'INJECTION_FAILED',
    };
  }
  const message = mode === 'selection' ? { type: 'EXTRACT_SELECTION' } : { type: 'EXTRACT' };
  try {
    return (await chrome.tabs.sendMessage(tabId, message)) as ContentResponse;
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : 'No response from page',
      code: 'INJECTION_FAILED',
    };
  }
}

/** Map an extraction status to an error response when a capture can't proceed. */
function extractionToError(status: string, note?: string): ErrResponse | null {
  if (status === 'unsupported') return err(note ?? 'Page not supported.', 'UNSUPPORTED_PAGE');
  if (status === 'empty') return err(note ?? 'No readable content on this page.', 'EMPTY');
  if (status === 'error') return err(note ?? 'Extraction failed.', 'INJECTION_FAILED');
  return null; // ok or partial are acceptable
}

// --- Message router ---------------------------------------------------------

async function handle(request: Request): Promise<Response> {
  switch (request.type) {
    case 'GET_STATE': {
      const state = await repo.loadState();
      return { ok: true, data: { state } };
    }

    case 'SET_STATE': {
      await repo.saveState(request.state);
      return { ok: true, data: { state: request.state } };
    }

    case 'GET_ACTIVE_TAB': {
      const tab = toTabInfo(await getActiveTab());
      return { ok: true, data: { tab } };
    }

    case 'LIST_RECENT': {
      const records = await repo.recent(request.limit ?? 20);
      return { ok: true, data: { records } };
    }

    case 'GET_RECORD': {
      const record = await repo.byId(request.id);
      return { ok: true, data: { record } };
    }

    case 'DELETE_RECORD': {
      const deleted = await repo.delete(request.id);
      return { ok: true, data: { deleted } };
    }

    case 'CAPTURE': {
      const state: CaptureState = await repo.loadState();
      if (!canCapture(state)) {
        return err(
          state === 'paused'
            ? 'Capture is paused. Resume to capture this page.'
            : 'Capture is stopped. Start capture to save pages.',
          state === 'paused' ? 'PAUSED' : 'STOPPED',
        );
      }

      const tabId = request.tab.id;
      if (typeof tabId !== 'number') return err('No active tab available.', 'NO_TAB');

      const url = request.tab.url ?? '';
      if (isRestrictedUrl(url)) {
        return err('This page is restricted by Chrome and cannot be captured.', 'UNSUPPORTED_PAGE');
      }

      const youtube = isYouTubeUrl(url);
      const extraction = await runExtraction(tabId, request.captureType);
      if (!extraction.ok) {
        return err(
          extraction.error,
          (extraction.code as ErrResponse['code']) ?? 'INJECTION_FAILED',
        );
      }
      const data = extraction.data;

      // Selection with nothing selected: guide the user, don't silently swap.
      if (request.captureType === 'selection' && !data.selectedText) {
        return err(
          'No text is selected. Select some text, or use “Capture page” for the whole page.',
          'EMPTY',
        );
      }

      const blocking = extractionToError(data.status, data.note);
      if (blocking && !youtube) return blocking;

      let record: CaptureRecord = buildRecord({
        tab: request.tab,
        extraction: youtube ? { ...data, status: 'partial' } : data,
        captureType: request.captureType,
        selectedText: data.selectedText,
        surroundingContext: data.surroundingContext,
      });
      if (youtube) {
        record.note =
          'YouTube: captured title/URL and any visible text only. Transcripts are not ' +
          'extracted (no supported, permitted mechanism).';
      }

      try {
        record = await repo.save(record);
      } catch {
        return err('Failed to save the capture locally.', 'STORAGE_ERROR');
      }

      // Optional, non-fatal local backend sync (disabled by default).
      const cfg = await loadBackendConfig();
      if (cfg.enabled) void sendToBackend(record, cfg);

      return { ok: true, data: { record } };
    }

    default:
      return err('Unknown request.', 'INVALID_MESSAGE');
  }
}

chrome.runtime.onMessage.addListener((message: unknown, _sender, sendResponse) => {
  if (!isValidMessage(message)) {
    sendResponse(err('Invalid message.', 'INVALID_MESSAGE'));
    return;
  }
  // Route async; return true to keep the message channel open.
  handle(message)
    .then(sendResponse)
    .catch((e: unknown) => {
      sendResponse(err(e instanceof Error ? e.message : 'Unexpected error'));
    });
  return true;
});

