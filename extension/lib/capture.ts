// RecallAI — capture record builder (Module 2, Tasks 2.6–2.7)
//
// Pure function that turns tab info + an extraction result into a validated
// CaptureRecord. Kept separate from chrome.* APIs so it is unit-testable.

import type { CaptureRecord, CaptureType, ExtractionResult, TabInfo } from '../types';
import { domainFromUrl } from './domain';
import { makeId } from './limits';

export interface BuildRecordInput {
  tab: TabInfo;
  extraction: ExtractionResult;
  captureType: CaptureType;
  selectedText?: string;
  surroundingContext?: string;
  /** Injectable clock for deterministic tests. */
  now?: () => Date;
  /** Injectable id factory for deterministic tests. */
  idFactory?: () => string;
}

/** Build a structured CaptureRecord. Never fabricates content. */
export function buildRecord(input: BuildRecordInput): CaptureRecord {
  const { tab, extraction, captureType } = input;
  const now = input.now ?? (() => new Date());
  const idFactory = input.idFactory ?? makeId;

  const url = tab.url ?? '';
  const domain = domainFromUrl(url) ?? 'unknown';

  const record: CaptureRecord = {
    id: idFactory(),
    title: tab.title?.trim() || domain || 'Untitled',
    url,
    domain,
    capturedAt: now().toISOString(),
    captureType,
    extractedText:
      captureType === 'selection'
        ? input.selectedText ?? extraction.selectedText ?? ''
        : extraction.text,
    status: extraction.status,
    contentLength:
      captureType === 'selection'
        ? (input.selectedText ?? extraction.selectedText ?? '').length
        : extraction.text.length,
  };

  if (captureType === 'selection') {
    const sel = input.selectedText ?? extraction.selectedText;
    const ctx = input.surroundingContext ?? extraction.surroundingContext;
    if (sel) record.selectedText = sel;
    if (ctx) record.surroundingContext = ctx;
  }
  if (extraction.note) record.note = extraction.note;

  return record;
}
