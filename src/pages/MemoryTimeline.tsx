import { useEffect, useState } from 'react';
import MemoryCard from '../components/MemoryCard';
import { EmptyState, ErrorState, LoadingState, NoMatchesState } from '../components/UIStates';
import { listMemories } from '../lib/memoriesApi';
import type { Memory } from '../data/types';

/** Memory Timeline — real records are always loaded from the local API. */
export default function MemoryTimeline() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [domain, setDomain] = useState('');
  const [sourceType, setSourceType] = useState('');
  const [page, setPage] = useState(1);
  const [refreshToken, setRefreshToken] = useState(0);
  const pageSize = 12;
  const hasFilters = Boolean(query.trim() || fromDate || toDate || domain.trim() || sourceType);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError('');
    listMemories(
      {
        q: query.trim(),
        from_date: fromDate,
        to_date: toDate,
        domain: domain.trim(),
        source_type: sourceType as 'browser' | 'transcript' | 'note' | undefined,
        page,
        page_size: pageSize,
      },
      controller.signal,
    )
      .then((result) => {
        setMemories(result.items);
        setTotal(result.total);
        setTotalPages(result.total_pages);
      })
      .catch((requestError: unknown) => {
        if (!controller.signal.aborted) {
          setError(requestError instanceof Error ? requestError.message : 'Could not load memories.');
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [query, fromDate, toDate, domain, sourceType, page, pageSize, refreshToken]);

  const setFilter = (setter: (value: string) => void, value: string) => {
    setter(value);
    setPage(1);
  };

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-ink">Memory Timeline</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Browse locally stored captures, transcripts, and notes.
        </p>
      </div>

      <div className="mb-6 rounded-2xl border border-slate-100 bg-surface p-4 shadow-card">
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          <div>
            <label htmlFor="timeline-search" className="sr-only">Search memories</label>
            <input
              id="timeline-search"
              type="search"
              value={query}
              onChange={(event) => setFilter(setQuery, event.target.value)}
              placeholder="Search titles and saved content"
              className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm text-ink placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
            />
          </div>
          <div>
            <label htmlFor="timeline-source" className="sr-only">Filter by source type</label>
            <select
              id="timeline-source"
              value={sourceType}
              onChange={(event) => setFilter(setSourceType, event.target.value)}
              className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-ink focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
            >
              <option value="">All source types</option>
              <option value="browser">Browser capture</option>
              <option value="transcript">Transcript</option>
              <option value="note">Manual note</option>
            </select>
          </div>
          <div>
            <label htmlFor="timeline-domain" className="sr-only">Filter by domain</label>
            <input
              id="timeline-domain"
              value={domain}
              onChange={(event) => setFilter(setDomain, event.target.value)}
              placeholder="Filter by domain"
              className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-ink focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
            />
          </div>
          <div>
            <label htmlFor="timeline-from-date" className="mb-1 block text-xs text-ink-muted">From date</label>
            <input
              id="timeline-from-date"
              type="date"
              value={fromDate}
              onChange={(event) => setFilter(setFromDate, event.target.value)}
              className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-ink"
            />
          </div>
          <div>
            <label htmlFor="timeline-to-date" className="mb-1 block text-xs text-ink-muted">To date</label>
            <input
              id="timeline-to-date"
              type="date"
              value={toDate}
              onChange={(event) => setFilter(setToDate, event.target.value)}
              className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-ink"
            />
          </div>
        </div>
        <div className="mt-3 flex items-center justify-between text-xs text-ink-muted">
          <span>{total} {total === 1 ? 'memory' : 'memories'}</span>
          {hasFilters && (
            <button
              type="button"
              onClick={() => {
                setQuery('');
                setSourceType('');
                setDomain('');
                setFromDate('');
                setToDate('');
                setPage(1);
              }}
              className="font-medium text-brand-700 hover:underline"
            >Clear filters</button>
          )}
        </div>
      </div>

      {loading ? (
        <LoadingState label="Loading saved memories…" />
      ) : error ? (
        <ErrorState message={error} onRetry={() => setRefreshToken((value) => value + 1)} />
      ) : total === 0 && hasFilters ? (
        <NoMatchesState query={query || domain || 'current filters'} />
      ) : total === 0 ? (
        <EmptyState
          title="No memories yet"
          description="Browser captures, transcripts, and manual notes saved to this device will appear here."
        />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2">
            {memories.map((memory) => <MemoryCard key={memory.id} memory={memory} />)}
          </div>
          <div className="mt-6 flex items-center justify-between">
            <span className="text-sm text-ink-muted">Page {page} of {totalPages}</span>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage((value) => Math.max(1, value - 1))}
                className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50"
              >Previous</button>
              <button
                type="button"
                disabled={page >= totalPages}
                onClick={() => setPage((value) => value + 1)}
                className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50"
              >Next</button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
