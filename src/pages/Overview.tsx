import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import StatCard from '../components/StatCard';
import MemoryCard from '../components/MemoryCard';
import { EmptyState } from '../components/UIStates';
import { useMemories } from '../state/MemoriesContext';
import { activitySummary } from '../data/mockData';
import type { SourceType } from '../data/types';

const filters: Array<{ key: string; label: string; type?: SourceType }> = [
  { key: 'all', label: 'All Sources' },
  { key: 'article', label: 'Articles', type: 'article' },
  { key: 'web-link', label: 'Web Links', type: 'web-link' },
  { key: 'markdown-note', label: 'Markdown Notes', type: 'markdown-note' },
  { key: 'code', label: 'Code & Terminals', type: 'code' },
];

/**
 * Overview — the landing dashboard. Shows the activity summary, a search entry
 * point, quick access to Ask RecallAI, capture status, recent memories, and
 * source/privacy indicators. Mirrors the approved Stitch Overview design.
 */
export default function Overview() {
  const { memories } = useMemories();
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');

  const recent = useMemo(() => {
    let list = memories;
    const active = filters.find((f) => f.key === filter);
    if (active?.type) list = list.filter((m) => m.sourceType === active.type);
    if (query.trim()) {
      const q = query.toLowerCase();
      list = list.filter(
        (m) =>
          m.title.toLowerCase().includes(q) ||
          m.excerpt.toLowerCase().includes(q) ||
          m.tags.join(' ').toLowerCase().includes(q),
      );
    }
    return list.slice(0, 6);
  }, [memories, filter, query]);

  return (
    <div className="mx-auto max-w-6xl">
      {/* Page header */}
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-ink">Overview</h1>
          <p className="mt-1 text-sm text-ink-muted">
            Your on-device cognitive repository and real-time capture stream.
          </p>
        </div>
        <CaptureStatusChip />
      </div>

      {/* Search + quick access */}
      <div className="mb-6 grid gap-4 lg:grid-cols-3">
        <div className="rounded-2xl border border-slate-100 bg-surface p-5 shadow-card lg:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="inline-flex items-center gap-2 text-sm font-semibold text-ink">
              <span aria-hidden="true">🔎</span> Universal Context Search
            </h2>
            <span className="rounded bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700">
              Indexed with HNSW
            </span>
          </div>
          <label htmlFor="overview-search" className="sr-only">
            Search memories
          </label>
          <input
            id="overview-search"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search memories, transcripts, visited links, and markdown"
            className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm text-ink placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
          />
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium text-ink-muted">Filter:</span>
            {filters.map((f) => (
              <button
                key={f.key}
                type="button"
                onClick={() => setFilter(f.key)}
                aria-pressed={filter === f.key}
                className={[
                  'rounded-full px-3 py-1 text-xs font-medium ring-1 ring-inset transition',
                  filter === f.key
                    ? 'bg-brand-700 text-white ring-brand-700'
                    : 'bg-white text-ink-muted ring-slate-200 hover:ring-brand-200',
                ].join(' ')}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {/* Ask RecallAI quick access */}
        <Link
          to="/ask"
          className="flex flex-col justify-between rounded-2xl bg-gradient-to-br from-brand-600 to-brand-700 p-5 text-white shadow-card transition hover:brightness-110"
        >
          <div>
            <span className="inline-block rounded-full bg-white/20 px-2 py-0.5 text-xs font-medium">
              Runs 100% On-Device
            </span>
            <h2 className="mt-3 text-lg font-bold">Ask RecallAI</h2>
            <p className="mt-1 text-sm text-white/80">
              Synthesize or query your local vault with a privacy-preserving mock LLM.
            </p>
          </div>
          <span className="mt-4 inline-flex items-center gap-1 text-sm font-semibold">
            Start Synthesis <span aria-hidden="true">→</span>
          </span>
        </Link>
      </div>

      {/* Activity summary */}
      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon="🧠"
          label="Total Memories"
          value={activitySummary.totalMemories.toLocaleString()}
          sub="Indexed locally in SQLite Vector"
          footer={
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200">
              <div className="h-full w-[18%] rounded-full bg-brand-500" />
            </div>
          }
        />
        <StatCard
          icon="⚡"
          label="Captured This Week"
          value={activitySummary.capturedThisWeek}
          sub="Across browser, apps, and OCR"
        />
        <StatCard
          icon="🔗"
          label="Sources Connected"
          value={`${activitySummary.sourcesConnected} all synchronized`}
          sub={activitySummary.sources.join(' • ')}
        />
        <StatCard
          icon="✅"
          label="Last Ingestion"
          value={activitySummary.lastIngestionLabel}
          sub={activitySummary.lastIngestionUrl}
        />
      </div>

      {/* Recent memories */}
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-ink">
          Recent Memories{' '}
          <span className="ml-1 align-middle text-xs font-medium text-ink-muted">12 today</span>
        </h2>
        <Link
          to="/timeline"
          className="inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:underline"
        >
          Open Timeline <span aria-hidden="true">→</span>
        </Link>
      </div>

      {recent.length === 0 ? (
        memories.length === 0 ? (
          <EmptyState
            title="No memories yet"
            description="Start capturing pages and notes from the browser extension. Everything stays on this device."
            action={
              <Link
                to="/privacy"
                className="rounded-lg bg-brand-700 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600"
              >
                Review capture settings
              </Link>
            }
          />
        ) : (
          <EmptyState
            title="No matches"
            description="No recent memories match your search or filter."
            action={
              <button
                type="button"
                onClick={() => {
                  setQuery('');
                  setFilter('all');
                }}
                className="rounded-lg bg-brand-700 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600"
              >
                Clear filters
              </button>
            }
          />
        )
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {recent.map((m) => (
            <MemoryCard key={m.id} memory={m} />
          ))}
        </div>
      )}
    </div>
  );
}

/** Small capture-status chip reused in the Overview header. */
function CaptureStatusChip() {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-100 bg-surface px-3 py-2 text-xs shadow-card">
      <span className="inline-flex items-center gap-1.5 rounded-full bg-safe-100 px-2.5 py-1 font-medium text-safe-700">
        <span className="inline-block h-2 w-2 rounded-full bg-safe-500" aria-hidden="true" />
        Active Capture
      </span>
      <span className="text-ink-muted">Local Sandbox API: 3.4ms tick</span>
    </div>
  );
}
