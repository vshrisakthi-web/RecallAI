import { describe, it, expect } from 'vitest';
import { domainFromUrl, isRestrictedUrl, isYouTubeUrl } from '../lib/domain';

describe('domain helpers (Tasks 2.4, 2.5)', () => {
  it('derives domains from http(s) URLs', () => {
    expect(domainFromUrl('https://arxiv.org/abs/123')).toBe('arxiv.org');
    expect(domainFromUrl('http://sub.example.com:8080/x')).toBe('sub.example.com');
  });

  it('returns null for non-http(s) or unparseable URLs', () => {
    expect(domainFromUrl('chrome://extensions')).toBeNull();
    expect(domainFromUrl('about:blank')).toBeNull();
    expect(domainFromUrl(undefined)).toBeNull();
    expect(domainFromUrl('not a url')).toBeNull();
  });

  it('flags restricted pages we must not inject into', () => {
    expect(isRestrictedUrl('chrome://extensions')).toBe(true);
    expect(isRestrictedUrl('https://chrome.google.com/webstore/x')).toBe(true);
    expect(isRestrictedUrl('https://chromewebstore.google.com/detail/x')).toBe(true);
    expect(isRestrictedUrl('chrome-extension://abc/page.html')).toBe(true);
    expect(isRestrictedUrl('https://example.com')).toBe(false);
    expect(isRestrictedUrl(undefined)).toBe(true);
  });

  it('detects YouTube URLs', () => {
    expect(isYouTubeUrl('https://www.youtube.com/watch?v=abc')).toBe(true);
    expect(isYouTubeUrl('https://youtu.be/abc')).toBe(true);
    expect(isYouTubeUrl('https://vimeo.com/123')).toBe(false);
    expect(isYouTubeUrl('https://notyoutube.com.evil/test')).toBe(false);
  });
});
