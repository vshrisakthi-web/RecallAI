// RecallAI — content script (Module 2, Tasks 2.5, 2.7)
//
// Injected on demand (via chrome.scripting.executeScript) only after the user
// clicks Capture. It reads the current permitted page and replies with a
// structured extraction result. It NEVER uploads anything and never reads form
// control values (extraction strips inputs/passwords first).

import { extractReadable, extractSelection } from '../lib/extract';
import type { ContentRequest, ContentResponse } from '../lib/messages';

function respond(res: ContentResponse, sendResponse: (r: ContentResponse) => void) {
  sendResponse(res);
}

/** Find the text of the paragraph/heading containing the current selection. */
function findSurroundingContext(): string | null {
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0) return null;
  let node: Node | null = sel.getRangeAt(0).commonAncestorContainer;
  while (node && node.nodeType !== Node.ELEMENT_NODE) {
    node = node.parentNode;
  }
  const el = node as Element | null;
  if (!el) return null;
  const block = el.closest('p, li, h1, h2, h3, h4, h5, h6, blockquote, td, pre');
  return block ? block.textContent : el.textContent;
}

chrome.runtime.onMessage.addListener((message: ContentRequest, _sender, sendResponse) => {
  if (!message || typeof message !== 'object') return;

  if (message.type === 'EXTRACT') {
    try {
      const result = extractReadable(document);
      respond({ ok: true, data: result }, sendResponse);
    } catch (e) {
      respond(
        { ok: false, error: e instanceof Error ? e.message : 'Extraction failed', code: 'ERROR' },
        sendResponse,
      );
    }
    return true; // async response
  }

  if (message.type === 'EXTRACT_SELECTION') {
    try {
      const { selectedText, surroundingContext } = extractSelection(
        () => window.getSelection()?.toString() ?? '',
        findSurroundingContext,
      );
      const data: import('../types').ExtractionResult = {
        status: selectedText ? 'ok' : 'empty',
        text: selectedText,
        headings: [],
        truncated: false,
        note: selectedText ? undefined : 'No text is currently selected.',
        selectedText: selectedText || undefined,
        surroundingContext,
      };
      respond({ ok: true, data }, sendResponse);
    } catch (e) {
      respond(
        { ok: false, error: e instanceof Error ? e.message : 'Selection failed', code: 'ERROR' },
        sendResponse,
      );
    }
    return true;
  }
});
