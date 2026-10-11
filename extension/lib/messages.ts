// RecallAI — typed message contracts (Module 2, Task 2.9)
//
// Every message between popup ↔ background ↔ content script is a discriminated
// union with an explicit `type`. `isValidMessage` guards incoming messages so a
// malformed or unexpected payload is rejected before processing.

import type { CaptureRecord, CaptureState, ExtractionResult, TabInfo } from '../types';

/** Messages the popup/panel send TO the background service worker. */
export type Request =
  | { type: 'GET_STATE' }
  | { type: 'SET_STATE'; state: CaptureState }
  | { type: 'GET_ACTIVE_TAB' }
  | { type: 'CAPTURE'; tab: TabInfo; captureType: 'full-page' | 'selection' }
  | { type: 'LIST_RECENT'; limit?: number }
  | { type: 'GET_RECORD'; id: string }
  | { type: 'DELETE_RECORD'; id: string };

/** Messages the background worker sends INTO a page's content script. */
export type ContentRequest = { type: 'EXTRACT' } | { type: 'EXTRACT_SELECTION' };

/** Successful response shapes, keyed by request type. */
export interface Responses {
  GET_STATE: { state: CaptureState };
  SET_STATE: { state: CaptureState };
  GET_ACTIVE_TAB: { tab: TabInfo | null };
  CAPTURE: { record: CaptureRecord };
  LIST_RECENT: { records: CaptureRecord[] };
  GET_RECORD: { record: CaptureRecord | null };
  DELETE_RECORD: { deleted: boolean };
}

/** A successful envelope: `ok: true` plus a typed payload. */
export interface OkResponse<T extends keyof Responses> {
  ok: true;
  data: Responses[T];
}

/** An error envelope: `ok: false` plus a message. */
export interface ErrResponse {
  ok: false;
  error: string;
  /** Machine-readable reason so the UI can show tailored guidance. */
  code?:
    | 'PAUSED'
    | 'STOPPED'
    | 'NO_TAB'
    | 'UNSUPPORTED_PAGE'
    | 'INJECTION_FAILED'
    | 'EMPTY'
    | 'STORAGE_ERROR'
    | 'NO_RECEIVER'
    | 'INVALID_MESSAGE';
}

export type Response<T extends keyof Responses = keyof Responses> =
  | OkResponse<T>
  | ErrResponse;

/** The content script's reply payload (the raw extraction result). */
export type ContentResponse =
  | { ok: true; data: ExtractionResult }
  | { ok: false; error: string; code?: string };

const REQUEST_TYPES: ReadonlySet<string> = new Set<Request['type']>([
  'GET_STATE',
  'SET_STATE',
  'GET_ACTIVE_TAB',
  'CAPTURE',
  'LIST_RECENT',
  'GET_RECORD',
  'DELETE_RECORD',
]);

const CAPTURE_STATES: ReadonlySet<string> = new Set<CaptureState>([
  'active',
  'paused',
  'stopped',
]);

/**
 * Validate an arbitrary value as a background `Request`. Returns the narrowed
 * value or null. Deliberately strict: unknown types are rejected.
 */
export function isValidMessage(value: unknown): value is Request {
  if (typeof value !== 'object' || value === null) return false;
  const msg = value as { type?: unknown };
  if (typeof msg.type !== 'string' || !REQUEST_TYPES.has(msg.type)) return false;

  switch (msg.type) {
    case 'SET_STATE': {
      const s = (value as { state?: unknown }).state;
      return typeof s === 'string' && CAPTURE_STATES.has(s);
    }
    case 'CAPTURE': {
      const t = (value as { captureType?: unknown }).captureType;
      return t === 'full-page' || t === 'selection';
    }
    case 'GET_RECORD':
    case 'DELETE_RECORD': {
      return typeof (value as { id?: unknown }).id === 'string';
    }
    default:
      return true;
  }
}
