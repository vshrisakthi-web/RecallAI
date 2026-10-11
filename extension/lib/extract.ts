// RecallAI — readable text extraction (Module 2, Task 2.5)
//
// A dependency-free readability heuristic that runs on a `Document`. It:
//  - strips scripts/styles/nav/aside/footer/form/header chrome,
//  - removes editable inputs, password fields, and form controls (never captured),
//  - prefers <article>/<main>, else <body>,
//  - preserves headings and paragraphs in document order,
//  - applies a documented size limit.
//
// It is intentionally DOM-only (no chrome.* APIs) so it is unit-testable with
// jsdom fixtures and reusable inside the content script.

import type { ExtractionResult } from '../types';
import { MAX_HEADINGS, MAX_TEXT_LENGTH } from './limits';

const STRIP_SELECTORS = [
  'script',
  'style',
  'noscript',
  'template',
  'svg',
  'nav',
  'aside',
  'footer',
  'header',
  'form',
  'button',
  'iframe',
  '[aria-hidden="true"]',
  '[hidden]',
  // Navigation / chrome by common class/id names.
  '.nav',
  '.navbar',
  '.sidebar',
  '.menu',
  '.header',
  '.footer',
  '.advert',
  '.ads',
  '.cookie',
  '.banner',
  '#nav',
  '#sidebar',
  '#comments',
];

/** Elements whose text we treat as body content. */
const BLOCK_SELECTOR = 'h1,h2,h3,h4,h5,h6,p,li,blockquote,pre,td,th';

function normalizeWhitespace(text: string): string {
  return text.replace(/\s+/g, ' ').trim();
}

/**
 * Extract readable main content from a document. Never reads form control values
 * (inputs are removed before scanning). Returns a structured result.
 */
export function extractReadable(doc: Document): ExtractionResult {
  // Work on a clone so we never mutate the live page.
  const root = doc.body ? doc.body.cloneNode(true) as DocumentFragment : null;
  if (!root) {
    return { status: 'empty', text: '', headings: [], truncated: false, note: 'No <body> found.' };
  }

  // Remove non-content elements, including all form controls (privacy: never
  // capture passwords, inputs, tokens).
  const removeSel = STRIP_SELECTORS.concat([
    'input',
    'textarea',
    'select',
    'option',
    'label',
  ]);
  removeSel.forEach((sel) => {
    root.querySelectorAll(sel).forEach((el) => el.remove());
  });

  // Prefer a main/article container if present.
  const preferred = root.querySelector('article, main, [role="main"]');
  const scope: ParentNode = preferred ?? root;

  const headings: string[] = [];
  const parts: string[] = [];
  let truncated = false;
  let total = 0;

  const blocks = Array.from(scope.querySelectorAll(BLOCK_SELECTOR));
  for (const el of blocks) {
    const text = normalizeWhitespace(el.textContent ?? '');
    if (!text) continue;

    const isHeading = /^H[1-6]$/.test(el.tagName);
    if (isHeading && headings.length < MAX_HEADINGS) {
      headings.push(text);
    }

    if (total >= MAX_TEXT_LENGTH) {
      truncated = true;
      break;
    }
    const remaining = MAX_TEXT_LENGTH - total;
    if (text.length > remaining) {
      parts.push(text.slice(0, remaining));
      total += remaining;
      truncated = true;
      break;
    }
    parts.push(text);
    total += text.length;
  }

  const text = parts.join('\n\n').slice(0, MAX_TEXT_LENGTH);

  if (text.length === 0) {
    return {
      status: 'empty',
      text: '',
      headings,
      truncated: false,
      note: 'No readable main content found on this page.',
    };
  }

  return {
    status: 'ok',
    text,
    headings,
    truncated,
    note: truncated ? `Text truncated to ${MAX_TEXT_LENGTH} characters.` : undefined,
  };
}

/**
 * Extract a user's current text selection plus the surrounding paragraph/heading
 * for context. `getSelection` is passed in so this stays testable.
 */
export function extractSelection(
  getSelectionText: () => string,
  findContainerText: () => string | null,
): { selectedText: string; surroundingContext?: string } {
  const selectedText = (getSelectionText() ?? '').trim();
  const surrounding = findContainerText();
  const surroundingContext = surrounding ? normalizeWhitespace(surrounding) : undefined;
  return { selectedText, surroundingContext };
}
