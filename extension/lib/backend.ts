// RecallAI — optional local backend adapter (Module 2, Task 2.9)
//
// Module 1/2 establish NO confirmed backend. This adapter is fully isolated and
// DISABLED by default. It only ever sends to a localhost endpoint the user has
// explicitly configured, and the extension works fine when it is absent/offline.
// It is never called automatically — capture always saves locally first.

import type { CaptureRecord } from '../types';

export interface BackendConfig {
  /** e.g. "http://localhost:8787". Empty = disabled. */
  endpoint: string;
  enabled: boolean;
}

export const DEFAULT_BACKEND_CONFIG: BackendConfig = { endpoint: '', enabled: false };

export interface BackendResult {
  sent: boolean;
  error?: string;
}

/**
 * Attempt to POST a record to a configured LOCAL backend. Returns a result
 * object; never throws. Callers treat a failure as non-fatal (the record is
 * already stored locally).
 */
export async function sendToBackend(
  record: CaptureRecord,
  config: BackendConfig,
  fetchImpl: typeof fetch = fetch,
): Promise<BackendResult> {
  if (!config.enabled || !config.endpoint) {
    return { sent: false };
  }
  // Guard: only allow http(s) localhost targets (no remote upload by default).
  let url: URL;
  try {
    url = new URL(config.endpoint);
  } catch {
    return { sent: false, error: 'Invalid endpoint URL' };
  }
  const isLocal =
    url.hostname === 'localhost' ||
    url.hostname === '127.0.0.1' ||
    url.hostname === '[::1]';
  if (!isLocal || (url.protocol !== 'http:' && url.protocol !== 'https:')) {
    return { sent: false, error: 'Backend must be a localhost http(s) endpoint' };
  }

  try {
    const res = await fetchImpl(url.toString(), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(record),
    });
    if (!res.ok) return { sent: false, error: `Backend responded ${res.status}` };
    return { sent: true };
  } catch (e) {
    return { sent: false, error: e instanceof Error ? e.message : 'Network error' };
  }
}
