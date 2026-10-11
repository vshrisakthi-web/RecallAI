import { describe, it, expect, vi } from 'vitest';
import { sendToBackend, DEFAULT_BACKEND_CONFIG } from '../lib/backend';
import type { CaptureRecord } from '../types';

const record: CaptureRecord = {
  id: 'id',
  title: 't',
  url: 'https://e.com',
  domain: 'e.com',
  capturedAt: '2026-01-01T00:00:00.000Z',
  captureType: 'full-page',
  extractedText: 'body',
  status: 'ok',
  contentLength: 4,
};

describe('optional backend adapter (Task 2.9)', () => {
  it('is disabled by default and never calls fetch', async () => {
    const fetchMock = vi.fn();
    const res = await sendToBackend(record, DEFAULT_BACKEND_CONFIG, fetchMock as unknown as typeof fetch);
    expect(res.sent).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('rejects non-localhost endpoints (no remote upload)', async () => {
    const fetchMock = vi.fn();
    const res = await sendToBackend(
      record,
      { endpoint: 'https://api.evil.com/ingest', enabled: true },
      fetchMock as unknown as typeof fetch,
    );
    expect(res.sent).toBe(false);
    expect(res.error).toMatch(/localhost/i);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('posts to a configured localhost endpoint when enabled', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true } as Response);
    const res = await sendToBackend(
      record,
      { endpoint: 'http://localhost:8787/capture', enabled: true },
      fetchMock as unknown as typeof fetch,
    );
    expect(res.sent).toBe(true);
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('treats a network failure as non-fatal', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error('ECONNREFUSED'));
    const res = await sendToBackend(
      record,
      { endpoint: 'http://127.0.0.1:8787/capture', enabled: true },
      fetchMock as unknown as typeof fetch,
    );
    expect(res.sent).toBe(false);
    expect(res.error).toBe('ECONNREFUSED');
  });
});
