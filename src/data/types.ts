// RecallAI — core data model (Task 1.9)
// These types describe the shape of a "memory" and related concepts. They are the
// contract between the mock data layer today and a future real backend/API.

/** The kind of thing a memory was captured from. Drives the source badge + icon. */
export type SourceType =
  | 'article'
  | 'web-link'
  | 'markdown-note'
  | 'code'
  | 'browser'
  | 'transcript'
  | 'note';

/** A single stored memory item. In the MVP this is mock data only. */
export interface Memory {
  id: string;
  title: string;
  /** Short excerpt shown on cards / timeline. */
  excerpt: string;
  /** Full body shown on the Memory Detail screen. */
  content: string;
  sourceType: SourceType;
  /** Human-facing source name, e.g. "arxiv.org". */
  sourceName: string;
  /** Clickable origin URL (where available). */
  sourceUrl: string;
  /** ISO date-time string of capture. */
  capturedAt: string;
  /** Short relative label, e.g. "Today at 11:24 AM". */
  capturedLabel: string;
  tags: string[];
  /** True while the item lives only on the user's device (always true in MVP). */
  localOnly: boolean;
  /** Optional per-source extraction note, e.g. "OCR & PDF parsed". */
  extractNote?: string;
  sourceId?: string;
  domain?: string;
  sourceMetadata?: Record<string, unknown>;
  captureType?: string;
  selectedText?: string;
  surroundingContext?: string;
  extractionStatus?: string;
  requestId?: string;
  contentHash?: string;
}

/** Capture state shared by the extension popup and side panel. */
export type CaptureState = 'active' | 'paused' | 'stopped';

/** A source reference cited inside an Ask RecallAI answer. */
export interface SourceReference {
  memoryId: string;
  title: string;
  sourceName: string;
}

/** One turn in an Ask RecallAI conversation. */
export interface ChatTurn {
  id: string;
  question: string;
  /** Mock answer text. Always rendered with a visible "Mock answer" badge. */
  answer: string;
  references: SourceReference[];
}

/** Info about the page currently being viewed (side panel context). */
export interface CurrentPageContext {
  title: string;
  domain: string;
  url: string;
}

/** Privacy / capture preferences (Privacy Settings screen). */
export interface PrivacySettings {
  autoCapture: boolean;
  captureIncognito: boolean;
  excludeSensitivePages: boolean;
  requireConfirmationToDelete: boolean;
  /** Comma-separated list of page patterns to exclude from capture. */
  excludedPatterns: string[];
}
