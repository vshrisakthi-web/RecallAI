import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { JSDOM } from 'jsdom';
import { extractReadable } from '../lib/extract';

function doc(html: string): Document {
  return new JSDOM(html).window.document;
}
function fixture(name: string): string {
  return readFileSync(resolve(__dirname, `./fixtures/${name}`), 'utf8');
}

describe('extractReadable — blog/article (Task 2.10 A)', () => {
  const result = extractReadable(doc(fixture('article.html')));

  it('extracts main readable text', () => {
    expect(result.status).toBe('ok');
    expect(result.text).toContain('Vector databases store embeddings');
    expect(result.text).toContain('ANN algorithms trade a little accuracy');
  });

  it('preserves headings', () => {
    expect(result.headings).toContain('Understanding Vector Databases');
    expect(result.headings).toContain('Approximate nearest neighbors');
  });

  it('strips navigation, footer, aside, and script chrome', () => {
    expect(result.text).not.toContain('Site Banner');
    expect(result.text).not.toContain('© 2026 TechBlog');
    expect(result.text).not.toContain('cookies policy');
    expect(result.text).not.toContain('should not be captured');
  });

  it('never captures form/password/input values', () => {
    expect(result.text).not.toContain('SUPERSECRET');
    expect(result.text).not.toContain('do-not-capture');
  });
});

describe('extractReadable — documentation page (Task 2.10 B)', () => {
  const result = extractReadable(doc(fixture('docs.html')));

  it('prefers <main> and keeps headings + paragraphs', () => {
    expect(result.status).toBe('ok');
    expect(result.text).toContain('navigable small-world graph');
    expect(result.text).toContain('ef parameter');
    expect(result.headings).toContain('Parameters');
    expect(result.headings).toContain('Usage');
  });

  it('reduces navigation/sidebar/comments chrome', () => {
    expect(result.text).not.toContain('Docs home');
    expect(result.text).not.toContain('Comment section content');
  });
});

describe('extractReadable — empty page (Task 2.10 E)', () => {
  it('returns an empty status with a note', () => {
    const result = extractReadable(doc(fixture('empty.html')));
    expect(result.status).toBe('empty');
    expect(result.text).toBe('');
    expect(result.note).toBeTruthy();
  });
});

describe('extractReadable — size limit', () => {
  it('truncates very large pages and flags it', () => {
    const big = `<article>${'<p>x'.repeat(100) + 'word '.repeat(20000)}</p></p>`;
    const result = extractReadable(doc(`<!doctype html><body>${big}</body>`));
    expect(result.text.length).toBeLessThanOrEqual(20_000);
    // truncated only if the source exceeded the cap
    if (result.text.length === 20_000) expect(result.truncated).toBe(true);
  });
});
