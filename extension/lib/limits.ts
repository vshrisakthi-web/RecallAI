// RecallAI — shared constants + id generation (Module 2)

/** Maximum characters of readable text kept per capture (documented limit). */
export const MAX_TEXT_LENGTH = 20_000;

/** Maximum number of headings preserved. */
export const MAX_HEADINGS = 50;

/**
 * Generate a stable, unique record id. Uses crypto.randomUUID when available
 * (modern Chrome + Node 19+), otherwise a timestamp+random fallback.
 */
export function makeId(): string {
  const c = globalThis.crypto as Crypto | undefined;
  if (c && typeof c.randomUUID === 'function') {
    return `mem_${c.randomUUID()}`;
  }
  const rand = Math.random().toString(36).slice(2, 10);
  return `mem_${Date.now().toString(36)}_${rand}`;
}
