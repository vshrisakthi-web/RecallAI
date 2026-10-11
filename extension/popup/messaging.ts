// RecallAI — popup messaging bridge (Module 2)
//
// Thin typed wrapper over chrome.runtime.sendMessage so popup components don't
// hand-roll message objects. Falls back gracefully if chrome.* is unavailable
// (e.g. when the same code is previewed in a browser without the extension API).

import type { Request, Response, Responses } from '../lib/messages';

type ResponseFor<T extends keyof Responses> = Response<T>;

/** Send a typed request to the background worker and await the envelope. */
export async function send<T extends keyof Responses>(
  req: Request,
): Promise<ResponseFor<T>> {
  if (typeof chrome === 'undefined' || !chrome.runtime?.sendMessage) {
    return { ok: false, error: 'Extension runtime unavailable.', code: 'NO_RECEIVER' } as ResponseFor<T>;
  }
  try {
    return (await chrome.runtime.sendMessage(req)) as ResponseFor<T>;
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : 'Message failed',
      code: 'NO_RECEIVER',
    } as ResponseFor<T>;
  }
}
