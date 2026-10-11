// RecallAI — URL / domain helpers (Module 2, Task 2.4)

/**
 * Derive a display domain from a URL. Returns null for unparseable URLs and for
 * chrome:// and extension-internal pages so callers can treat them as restricted.
 */
export function domainFromUrl(url: string | undefined): string | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    // chrome://, chrome-extension://, about:, edge:// etc. are restricted.
    if (u.protocol !== 'http:' && u.protocol !== 'https:') return null;
    return u.hostname;
  } catch {
    return null;
  }
}

/**
 * True when a URL points at a page Chrome forbids script injection on
 * (chrome://, the Chrome Web Store, extension pages, etc.). We never attempt to
 * bypass these; the UI shows a clear "unsupported page" message instead.
 */
export function isRestrictedUrl(url: string | undefined): boolean {
  if (!url) return true;
  const restrictedPrefixes = [
    'chrome://',
    'chrome-extension://',
    'edge://',
    'about:',
    'https://chrome.google.com/webstore',
    'https://chromewebstore.google.com/',
    'view-source:',
  ];
  return restrictedPrefixes.some((p) => url.startsWith(p));
}

/** True when a URL looks like a YouTube watch/short page. */
export function isYouTubeUrl(url: string | undefined): boolean {
  if (!url) return false;
  try {
    const u = new URL(url);
    return /(^|\.)youtube\.com$/.test(u.hostname) || u.hostname === 'youtu.be';
  } catch {
    return false;
  }
}
