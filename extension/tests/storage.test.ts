import { describe, it, expect, beforeEach } from 'vitest';
import { CaptureRepository, type StorageLike } from '../lib/storage';
import type { CaptureRecord } from '../types';

/** In-memory stand-in for chrome.storage.local. */
function makeFakeStorage(): StorageLike & { dump: () => Record<string, unknown> } {
  const data: Record<string, unknown> = {};
  return {
    async get(keys) {
      const arr = Array.isArray(keys) ? keys : [keys];
      const out: Record<string, unknown> = {};
      for (const k of arr) if (k in data) out[k] = data[k];
      return out;
    },
    async set(items) {
      Object.assign(data, items);
    },
    async remove(keys) {
      const arr = Array.isArray(keys) ? keys : [keys];
      for (const k of arr) delete data[k];
    },
    dump: () => data,
  };
}

function rec(partial: Partial<CaptureRecord>): CaptureRecord {
  return {
    id: 'id',
    title: 't',
    url: 'https://e.com',
    domain: 'e.com',
    capturedAt: new Date().toISOString(),
    captureType: 'full-page',
    extractedText: 'body',
    status: 'ok',
    contentLength: 4,
    ...partial,
  };
}

/** Distinct content per id so the content-dedup does not collapse test rows. */
function unique(id: string): Partial<CaptureRecord> {
  return { id, title: id, extractedText: `body-${id}`, contentLength: `body-${id}`.length };
}

describe('CaptureRepository (Task 2.10 G)', () => {
  let storage: ReturnType<typeof makeFakeStorage>;
  let repo: CaptureRepository;
  beforeEach(() => {
    storage = makeFakeStorage();
    repo = new CaptureRepository(storage);
  });

  it('saves and retrieves records newest-first', async () => {
    await repo.save(rec(unique('a')));
    await repo.save(rec(unique('b')));
    const recent = await repo.recent();
    expect(recent.map((r) => r.id)).toEqual(['b', 'a']);
  });

  it('retrieves a record by id', async () => {
    await repo.save(rec(unique('x')));
    expect((await repo.byId('x'))?.title).toBe('x');
    expect(await repo.byId('nope')).toBeNull();
  });

  it('deletes a record and reports whether it existed', async () => {
    await repo.save(rec(unique('d')));
    expect(await repo.delete('d')).toBe(true);
    expect(await repo.delete('d')).toBe(false);
  });

  it('de-duplicates identical content (repeated clicks)', async () => {
    await repo.save(rec({ id: 'first', extractedText: 'same body' }));
    await repo.save(rec({ id: 'second', extractedText: 'same body' }));
    const recent = await repo.recent();
    expect(recent).toHaveLength(1);
  });

  it('persists and loads capture state, defaulting to active', async () => {
    expect(await repo.loadState()).toBe('active');
    await repo.saveState('paused');
    expect(await repo.loadState()).toBe('paused');
    await repo.saveState('stopped');
    expect(await repo.loadState()).toBe('stopped');
  });

  it('respects the recent() limit', async () => {
    await repo.save(rec(unique('1')));
    await repo.save(rec(unique('2')));
    await repo.save(rec(unique('3')));
    expect((await repo.recent(2)).map((r) => r.id)).toEqual(['3', '2']);
  });
});
