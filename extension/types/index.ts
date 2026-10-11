// RecallAI — Extension core types (Module 2)
//
// These types are the contract shared by the popup, background service worker,
// content script, local storage repository, and the optional backend adapter.
// They are intentionally independent of the dashboard's mock `Memory` type so
// the extension can evolve on its own.

/** Capture lifecycle state. Mirrors the dashboard's CaptureState vocabulary. */
export type CaptureState = 'active' | 'paused' | 'stopped';

/** Whether a capture is the whole page or a user selection. */
export type CaptureType = 'full-page' | 'selection';

/**
 * How well extraction went. Honest about partial results — we never fabricate
 * content that was not actually readable.
 */
export type ExtractionStatus =
  | 'ok' // readable text extracted
  | 'empty' // page had no readable main content
  | 'partial' // some fields unavailable (e.g. YouTube transcript)
  | 'unsupported' // restricted page (chrome://, Web Store) or injection denied
  | 'error'; // extraction failed unexpectedly

/** The raw readable content pulled from a page (before it becomes a record). */
export interface ExtractionResult {
  status: ExtractionStatus;
  /** Cleaned main readable text (may be empty). */
  text: string;
  /** Preserved headings found in the main content, in order. */
  headings: string[];
  /** True when the text was truncated to the size limit. */
  truncated: boolean;
  /** Human note explaining a partial/unsupported/empty status. */
  note?: string;
  /** For selection captures: the exact selected text. */
  selectedText?: string;
  /** For selection captures: surrounding paragraph/heading, when available. */
  surroundingContext?: string;
}

/** A structured memory record persisted in chrome.storage.local. */
export interface CaptureRecord {
  id: string;
  title: string;
  url: string;
  domain: string;
  /** ISO date-time string. */
  capturedAt: string;
  captureType: CaptureType;
  /** Cleaned main readable text (full-page) or the selected text. */
  extractedText: string;
  /** Selected text, only for selection captures. */
  selectedText?: string;
  /** Surrounding paragraph/heading for a selection, when available. */
  surroundingContext?: string;
  status: ExtractionStatus;
  /** Number of characters of extractedText (metadata; avoids re-measuring). */
  contentLength: number;
  /** Optional note (e.g. why a field was unavailable). */
  note?: string;
}

/** Minimal info about the active tab at capture time. */
export interface TabInfo {
  id?: number;
  title?: string;
  url?: string;
}
