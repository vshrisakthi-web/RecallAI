// RecallAI — local capture repository (Module 2, Task 2.9)
//
// Persistence layer over chrome.storage.local. Exposed behind a small
// `StorageLike` interface so tests can pass an in-memory fake instead of the
// real Chrome API. Provides save / recent / byId / delete, with de-duplication
// so rapid double-clicks don't create unintended duplicate records.

import type { CaptureRecord } from '../types';

/** The subset of chrome.storage.local we rely on. */
export interface StorageLike {
  get(keys: string | string[]): Promise<Record<string, unknown>>;
  set(items: Record<string, unknown>): Promise<void>;
  remove(keys: string | string[]): Promise<void>;
}

const RECORDS_KEY = 'recallai.records';
const STATE_KEY = 'recallai.state';
/** Newest-first cap so local storage can't grow without bound. */
const MAX_RECORDS = 500;

export class CaptureRepository {
  constructor(private readonly storage: StorageLike) {}

  /** Save a record. De-duplicates by id (updates in place) and by a content
   * fingerprint to avoid accidental duplicates from repeated clicks. */
  async save(record: CaptureRecord): Promise<CaptureRecord> {
    const { records } = await this.readAll();
    const fingerprint = fingerprintOf(record);
    const existingIndex = records.findIndex(
      (r) => r.id === record.id || fingerprintOf(r) === fingerprint,
    );

    if (existingIndex >= 0) {
      // Same content already stored — update in place, keep original position.
      records[existingIndex] = { ...records[existingIndex], ...record };
    } else {
      records.unshift(record);
    }

    const trimmed = records.slice(0, MAX_RECORDS);
    await this.storage.set({ [RECORDS_KEY]: trimmed });
    return record;
  }

  /** Most-recent-first list, limited. */
  async recent(limit = 20): Promise<CaptureRecord[]> {
    const { records } = await this.readAll();
    return records.slice(0, Math.max(0, limit));
  }

  /** A single record by id, or null. */
  async byId(id: string): Promise<CaptureRecord | null> {
    const { records } = await this.readAll();
    return records.find((r) => r.id === id) ?? null;
  }

  /** Delete a record. Returns true if something was removed. */
  async delete(id: string): Promise<boolean> {
    const { records } = await this.readAll();
    const next = records.filter((r) => r.id !== id);
    if (next.length === records.length) return false;
    await this.storage.set({ [RECORDS_KEY]: next });
    return true;
  }

  /** Persist the capture state. */
  async saveState(state: 'active' | 'paused' | 'stopped'): Promise<void> {
    await this.storage.set({ [STATE_KEY]: state });
  }

  /** Read the capture state, defaulting to 'active'. */
  async loadState(): Promise<'active' | 'paused' | 'stopped'> {
    const bag = await this.storage.get(STATE_KEY);
    const s = bag[STATE_KEY];
    return s === 'active' || s === 'paused' || s === 'stopped' ? s : 'active';
  }

  private async readAll(): Promise<{ records: CaptureRecord[] }> {
    const bag = await this.storage.get(RECORDS_KEY);
    const raw = bag[RECORDS_KEY];
    if (!Array.isArray(raw)) return { records: [] };
    // Defensive: keep only objects that look like records.
    return { records: raw.filter(isRecordLike) as CaptureRecord[] };
  }
}

/** A cheap content fingerprint: same page + same text + same type = duplicate. */
function fingerprintOf(r: CaptureRecord): string {
  return `${r.url}::${r.captureType}::${r.extractedText.slice(0, 200)}`;
}

function isRecordLike(v: unknown): boolean {
  if (typeof v !== 'object' || v === null) return false;
  const r = v as Partial<CaptureRecord>;
  return typeof r.id === 'string' && typeof r.title === 'string' && typeof r.url === 'string';
}
