// RecallAI — mock data (Task 1.9)
//
// This is the ONLY place sample data lives. Components never hard-code sample
// content; they import from here. When a real backend arrives, replace the
// functions in this file with API calls — no component changes required.
//
// IMPORTANT: All AI answers below are MOCK. The UI must always label them as
// "Mock answer" so they are never mistaken for real AI output.

import type {
  CaptureState,
  ChatTurn,
  CurrentPageContext,
  Memory,
  PrivacySettings,
  SourceType,
} from './types';

/** Small helper so cards can show a coloured badge per source type. */
export const sourceMeta: Record<
  SourceType,
  { label: string; icon: string; badgeClass: string }
> = {
  article: { label: 'Article', icon: '📄', badgeClass: 'bg-blue-50 text-blue-700 ring-blue-200' },
  'web-link': { label: 'Web Link', icon: '🔗', badgeClass: 'bg-teal-50 text-teal-700 ring-teal-200' },
  'markdown-note': { label: 'Markdown Note', icon: '📝', badgeClass: 'bg-violet-50 text-violet-700 ring-violet-200' },
  code: { label: 'Code', icon: '💻', badgeClass: 'bg-emerald-50 text-emerald-700 ring-emerald-200' },
  browser: { label: 'Browser capture', icon: '🌐', badgeClass: 'bg-blue-50 text-blue-700 ring-blue-200' },
  transcript: { label: 'Transcript', icon: '🎙️', badgeClass: 'bg-amber-50 text-amber-700 ring-amber-200' },
  note: { label: 'Manual note', icon: '📝', badgeClass: 'bg-teal-50 text-teal-700 ring-teal-200' },
};

/** The mock memory set. Ordered newest-first to match the Overview/Timeline. */
export const memories: Memory[] = [
  {
    id: 'mem-001',
    title: 'Attention Mechanisms in Lightweight Vision Transformers',
    excerpt: 'MobileViT replaces convolutions in transformers with convolutions to achieve sub-...',
    content:
      'MobileViT replaces convolutions in transformers with convolutions to achieve sub-\nmillion parameter vision models that run on-device. The paper argues that local\ninductive bias plus global self-attention gives the best accuracy/latency trade-off\nfor mobile inference. Key takeaway for RecallAI: a local 3B model can plausibly power\noffline embeddings without cloud round-trips.',
    sourceType: 'article',
    sourceName: 'arxiv.org',
    sourceUrl: 'https://arxiv.org/abs/2405.04434',
    capturedAt: '2026-10-11T11:24:00',
    capturedLabel: 'Today at 11:24 AM',
    tags: ['#MachineLearning', '#Transformers', '#Research'],
    localOnly: true,
    extractNote: 'OCR & PDF parsed',
  },
  {
    id: 'mem-002',
    title: 'Q3 Design System Migration: Token Specs & Sync RFC',
    excerpt: 'RFC approved by core team. Deprecating legacy hex variables in favor of CSS variables semantics...',
    content:
      'RFC approved by core team. Deprecating legacy hex variables in favor of CSS\nvariables semantics. Migration is staged: tokens ship in the design package first,\nthen component updates roll out over two sprints. Dark mode is the first consumer\nof the new token contract.',
    sourceType: 'web-link',
    sourceName: 'linear.app',
    sourceUrl: 'https://linear.app/recallai/issue/design-tokens-rfc',
    capturedAt: '2026-10-11T10:45:00',
    capturedLabel: 'Today at 10:45 AM',
    tags: ['#Work', '#DesignSystem', '#Linear'],
    localOnly: true,
    extractNote: 'DOM snapshot saved',
  },
  {
    id: 'mem-003',
    title: 'Weekly 1:1 Reflections & Personal Knowledge Goals',
    excerpt: 'Ideas to explore: local-first vector retrieval using Ollama embeddings, zero cloud dependencies...',
    content:
      'Ideas to explore: local-first vector retrieval using Ollama embeddings, zero\ncloud dependencies for personal notes. Reflection: I read a lot but recall too\nlittle — the gap is retrieval, not capture. A privacy-first second brain should\nmake recall as fast as capture.',
    sourceType: 'markdown-note',
    sourceName: 'Obsidian Vault',
    sourceUrl: 'file:///vault/weekly/weekly-1-1.md',
    capturedAt: '2026-10-11T09:12:00',
    capturedLabel: 'Today at 09:12 AM',
    tags: ['#Notes', '#Journal', '#LocalFirst'],
    localOnly: true,
    extractNote: 'File watch sync',
  },
  {
    id: 'mem-004',
    title: 'The Economics of On-Device vs Cloud Inference',
    excerpt: 'Analyzing memory-bandwidth bottlenecks on M-series chips and the shift toward confidential local...',
    content:
      'Analyzing memory-bandwidth bottlenecks on M-series chips and the shift toward\nconfidential local compute. On-device inference avoids per-token cloud costs and\nkeeps sensitive text inside a hardware enclave. The trade-off is model size vs.\nunified-memory bandwidth.',
    sourceType: 'article',
    sourceName: 'stratechery.com',
    sourceUrl: 'https://stratechery.com/2026/on-device-inference',
    capturedAt: '2026-10-10T16:30:00',
    capturedLabel: 'Yesterday at 4:30 PM',
    tags: ['#AIHardware', '#Economics'],
    localOnly: true,
    extractNote: 'Reader View extracted',
  },
  {
    id: 'mem-005',
    title: 'sqlite-vss: Vector Search Extension Documentation',
    excerpt: 'Implementation notes on HNSW indexing directly inside SQLite with zero network overhead...',
    content:
      'Implementation notes on HNSW indexing directly inside SQLite with zero network\noverhead. Fast nearest-neighbour search over embeddings without a separate vector\ndatabase. This is the storage backbone candidate for RecallAI local search.',
    sourceType: 'code',
    sourceName: 'github.com',
    sourceUrl: 'https://github.com/asg017/sqlite-vss',
    capturedAt: '2026-10-10T14:15:00',
    capturedLabel: 'Yesterday at 2:15 PM',
    tags: ['#Engineering', '#Database'],
    localOnly: true,
    extractNote: 'Code AST indexed',
  },
  {
    id: 'mem-006',
    title: 'Design Tokens 2.0 - Dark & High Contrast Modes',
    excerpt: 'Component audit for accessible WCAG AAA compliance and border contrast across surface containers...',
    content:
      'Component audit for accessible WCAG AAA compliance and border contrast across\nsurface containers. Defines the accessible token tiers used by the RecallAI UI so\nthat the privacy indicators remain legible in both light and dark modes.',
    sourceType: 'web-link',
    sourceName: 'figma.com',
    sourceUrl: 'https://figma.com/file/recallai-design-tokens',
    capturedAt: '2026-10-09T11:00:00',
    capturedLabel: 'Yesterday at 11:00 AM',
    tags: ['#UIUX', '#Accessibility'],
    localOnly: true,
    extractNote: 'Screen OCR logged',
  },
];

/** Overview activity summary (mock). */
export const activitySummary = {
  totalMemories: 4829,
  totalMemoriesDelta: '+142',
  capturedThisWeek: 318,
  capturedThisWeekDeltaPct: 18,
  sourcesConnected: 5,
  sources: ['Chrome', 'Obsidian', 'Slack', 'VS Code'],
  lastIngestionLabel: '2 mins ago',
  lastIngestionUrl: 'arxiv.org/abs/2405.04434',
  storageUsedGb: 1.4,
  storageTotalGb: 8.0,
};

/** Default capture state shown on load. */
export const initialCaptureState: CaptureState = 'active';

/** Suggested questions for the empty Ask RecallAI / side panel state. */
export const suggestedQuestions = [
  'What did I read about on-device inference?',
  'Summarize my notes on local-first retrieval.',
  'Which design tokens did I save this week?',
];

/**
 * A tiny mock "ask" engine. Returns a canned answer built from the query so the
 * UI can demonstrate the flow WITHOUT any real AI. Callers must render the
 * result with a "Mock answer" badge.
 */
export function mockAsk(question: string, allMemories: Memory[]): ChatTurn {
  const q = question.trim();
  const keywords = q.toLowerCase().split(/\s+/).filter((w) => w.length > 3);
  const hits = allMemories
    .map((m) => {
      const haystack = `${m.title} ${m.excerpt} ${m.tags.join(' ')}`.toLowerCase();
      const score = keywords.reduce(
        (acc, w) => acc + (haystack.includes(w) ? 1 : 0),
        0,
      );
      return { m, score };
    })
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 3)
    .map((x) => x.m);

  const used = hits.length > 0 ? hits : allMemories.slice(0, 2);
  const answer =
    `Based on your locally stored memories, here is a mock summary for\n` +
    `"${q || 'your question'}". A real version would run an on-device model over\n` +
    `${used.length} matching ${used.length === 1 ? 'memory' : 'memories'}; this MVP\n` +
    `returns canned text so the interface can be demonstrated without any backend.`;

  return {
    id: `turn-${Date.now()}`,
    question: q || '(empty question)',
    answer,
    references: used.map((m) => ({
      memoryId: m.id,
      title: m.title,
      sourceName: m.sourceName,
    })),
  };
}

/** Pre-seeded conversation so the populated state is visible on first load. */
export const initialConversation: ChatTurn[] = [
  {
    id: 'turn-seed-1',
    question: 'What did I read about on-device inference?',
    answer:
      'You saved two items on on-device inference: the Stratechery piece on the\n' +
      'economics of on-device vs cloud inference, and notes on memory-bandwidth\n' +
      'bottlenecks on M-series chips. (Mock answer — no real model ran.)',
    references: [
      { memoryId: 'mem-004', title: 'The Economics of On-Device vs Cloud Inference', sourceName: 'stratechery.com' },
      { memoryId: 'mem-001', title: 'Attention Mechanisms in Lightweight Vision Transformers', sourceName: 'arxiv.org' },
    ],
  },
];

/** The page context shown in the side panel (mock "current tab"). */
export const currentPageContext: CurrentPageContext = {
  title: 'MobileViT: Lightweight Vision Transformers',
  domain: 'arxiv.org',
  url: 'https://arxiv.org/abs/2405.04434',
};

/** Default privacy settings (mock). */
export const defaultPrivacySettings: PrivacySettings = {
  autoCapture: true,
  captureIncognito: false,
  excludeSensitivePages: true,
  requireConfirmationToDelete: true,
  excludedPatterns: ['*://*.bank.com/*', '*://mail.*/*'],
};

