import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import MemoryCard from '../components/MemoryCard';
import { EmptyState, NoMatchesState } from '../components/UIStates';
import { useMemories } from '../state/MemoriesContext';
import type { SourceType } from '../data/types';

const sourceOptions: Array<{ value: 'all' | SourceType; label: string }> = [
  { value: 'all', label: 'All sources' },
  { value: 'article', label: 'Article' },
  { value: 'web-link', label: 'Web Link' },
  { value: 'markdown-note', label: 'Markdown Note' },
  { value: 'code', label: 'Code' },
];

const dateOptions = [
  { value: 'all', label: 'Any time' },
  { value: 'today', label: 'Today' },
  { value: 'week', label: 'This week' },
];

/**
 * Memory Timeline — the full chronological browse view with search, a source-type
 * filter, and a date filter. Cards open the Memory Detail view.
 */
export default function MemoryTimeline() {
  const { memories } = useMemories();
  const [query, setQuery] = useState('');
  const [source, setSource] = useState<'all' | SourceType>('all');
  const [date, setDate] = useState('all');

  const filtered = useMemo(() => {
    let list = memories;
    if (source !== 'all') list = list.filter((m) => m.sourceType === source);
    if (query.trim()) {
      const q = query.toLowerCase();
      list = list.filter(
        (m) =>
          m.title.toLowerCase().includes(q) ||
          m.excerpt.toLowerCase().includes(q) ||
          m.sourceName.toLowerCase().includes(q) ||
          m.tags.join(' ').toLowerCase().includes(q),
      );
    }
    if (date === 'today') list = list.filter((m) => m.capturedLabel.startsWith('Today'));
    // 'week' keeps everything: all mock data is within the current week.
    return list;
  }, [memories, source, query, date]);

  const hasQuery = query.trim().length > 0 || source !== 'all' || date !== 'all';

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-ink">Memory Timeline</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Browse everything you have captured, newest first. All items stay on this device.
        </p>
      </div>

      {/* Search + filters */}
      <div className="mb-6 rounded-2xl border border-slate-100 bg-surface p-4 shadow-card">
        <div className="grid gap-3 md:grid-cols-[1fr_auto_auto]">
          <div>
            <label htmlFor="timeline-search" className="sr-only">
              Search memories
            </label>
            <input
              id="timeline-search"
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by title, source, or tag"
              className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm text-ink placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
            />
          </div>
          <div>
            <label htmlFor="timeline-source" className="sr-only">
              Filter by source
            </label>
            <select
              id="timeline-source"
              value={source}
              onChange={(e) => setSource(e.target.value as 'all' | SourceType)}
              className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-ink focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
            >
              {sourceOptions.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="timeline-date" className="sr-only">
              Filter by date
            </label>
            <select
              id="timeline-date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-ink focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
            >
              {dateOptions.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="mt-3 flex items-center justify-between text-xs text-ink-muted">
          <span>
            {filtered.length} {filtered.length === 1 ? 'memory' : 'memories'}
          </span>
          {hasQuery && (
            <button
              type="button"
              onClick={() => {
                setQuery('');
                setSource('all');
                setDate('all');
              }}
              className="font-medium text-brand-700 hover:underline"
            >
              Clear filters
            </button>
          )}
        </div>
      </div>

      {/* Results */}
      {memories.length === 0 ? (
        <EmptyState
          title="No memories yet"
          description="Captured pages, notes, and links will appear here in chronological order."
          action={
            <Link
              to="/overview"
              className="rounded-lg bg-brand-700 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600"
            >
              Back to Overview
            </Link>
          }
        />
      ) : filtered.length === 0 ? (
        <NoMatchesState query={query || 'current filters'} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {filtered.map((m) => (
            <MemoryCard key={m.id} memory={m} />
          ))}
        </div>
      )}
    </div>
  );
}
