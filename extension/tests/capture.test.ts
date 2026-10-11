import { describe, it, expect } from 'vitest';
import { buildRecord } from '../lib/capture';
import type { ExtractionResult } from '../types';

const tab = { id: 7, title: 'Hello World', url: 'https://example.com/post' };
const okExtraction: ExtractionResult = {
  status: 'ok',
  text: 'Some readable body text.',
  headings: ['Hello'],
  truncated: false,
};

describe('buildRecord (Tasks 2.6–2.7)', () => {
  it('builds a full-page record with id + timestamp', () => {
    const r = buildRecord({
      tab,
      extraction: okExtraction,
      captureType: 'full-page',
      now: () => new Date('2026-01-02T03:04:05Z'),
      idFactory: () => 'mem_fixed',
    });
    expect(r.id).toBe('mem_fixed');
    expect(r.capturedAt).toBe('2026-01-02T03:04:05.000Z');
    expect(r.domain).toBe('example.com');
    expect(r.title).toBe('Hello World');
    expect(r.captureType).toBe('full-page');
    expect(r.extractedText).toBe('Some readable body text.');
    expect(r.contentLength).toBe('Some readable body text.'.length);
    expect(r.selectedText).toBeUndefined();
  });

  it('builds a selection record with selectedText + context', () => {
    const sel: ExtractionResult = {
      status: 'ok',
      text: 'chosen phrase',
      headings: [],
      truncated: false,
      selectedText: 'chosen phrase',
      surroundingContext: 'The surrounding paragraph that contains the chosen phrase.',
    };
    const r = buildRecord({
      tab,
      extraction: sel,
      captureType: 'selection',
      idFactory: () => 'mem_sel',
    });
    expect(r.captureType).toBe('selection');
    expect(r.selectedText).toBe('chosen phrase');
    expect(r.surroundingContext).toContain('surrounding paragraph');
    expect(r.extractedText).toBe('chosen phrase');
  });

  it('falls back to domain when title is missing', () => {
    const r = buildRecord({
      tab: { id: 1, url: 'https://sub.domain.org/x' },
      extraction: okExtraction,
      captureType: 'full-page',
      idFactory: () => 'id',
    });
    expect(r.title).toBe('sub.domain.org');
  });
});
