import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import SourceBadge from '../components/SourceBadge';
import { ErrorState, LoadingState } from '../components/UIStates';
import {
  deleteMemory as deleteMemoryApi,
  getMemory,
  summarizeMemory,
} from '../lib/memoriesApi';
import type { MemoryDetail as MemoryDetailData, MemorySummary } from '../lib/memoriesApi';

/**
 * Memory Detail — saved content and source details loaded from the local API.
 *
 */
export default function MemoryDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [detail, setDetail] = useState<MemoryDetailData | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);
  // AI summary state (Task 5.8) — user-initiated only, never automatic.
  const [summarizing, setSummarizing] = useState(false);
  const [summaryData, setSummaryData] = useState<MemorySummary | null>(null);
  const [summaryError, setSummaryError] = useState('');
  const summaryControllerRef = useRef<AbortController | null>(null);

  // Navigating to a different memory invalidates any in-flight or displayed
  // summary so a stale response for the previous memory can never appear.
  useEffect(() => {
    summaryControllerRef.current?.abort();
    summaryControllerRef.current = null;
    setSummaryData(null);
    setSummaryError('');
    setSummarizing(false);
    return () => summaryControllerRef.current?.abort();
  }, [id]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError('');
    if (id) {
      getMemory(id, controller.signal)
        .then(setDetail)
        .catch((requestError: unknown) => {
          if (!controller.signal.aborted) {
            setError(requestError instanceof Error ? requestError.message : 'Could not load this memory.');
          }
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    } else {
      setError('Memory ID is missing.');
      setLoading(false);
    }
    return () => controller.abort();
  }, [id, refreshToken]);

  if (loading) {
    return (
      <div className="mx-auto max-w-3xl">
        <LoadingState label="Loading memory…" />
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="mx-auto max-w-3xl">
        <ErrorState
          message={error || 'This memory could not be found. It may have been deleted.'}
          onRetry={() => setRefreshToken((value) => value + 1)}
        />
        <div className="mt-4 text-center">
          <Link to="/timeline" className="text-sm font-medium text-brand-700 hover:underline">
            ← Back to Timeline
          </Link>
        </div>
      </div>
    );
  }

  const { memory, source } = detail;
  const handleDelete = async () => {
    setDeleting(true);
    setError('');
    try {
      await deleteMemoryApi(memory.id);
      navigate('/timeline');
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not delete this memory.');
      setDeleting(false);
    }
  };

  const handleGenerateSummary = async () => {
    // Repeated clicks while a generation is running are ignored here and the
    // button is disabled in the markup as a second line of defence.
    if (summarizing || !detail) return;
    const controller = new AbortController();
    summaryControllerRef.current = controller;
    setSummarizing(true);
    setSummaryError('');
    try {
      const result = await summarizeMemory(memory.id, controller.signal);
      if (!controller.signal.aborted) setSummaryData(result);
    } catch (requestError) {
      if (!controller.signal.aborted) {
        setSummaryError(
          requestError instanceof Error ? requestError.message : 'Could not generate a summary.',
        );
      }
    } finally {
      if (!controller.signal.aborted) setSummarizing(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl">
      <Link
        to="/timeline"
        className="mb-4 inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:underline"
      >
        <span aria-hidden="true">←</span> Back to Timeline
      </Link>

      <article className="rounded-2xl border border-slate-100 bg-surface p-6 shadow-card">
        <div className="mb-4 flex items-center justify-between">
          <SourceBadge type={memory.sourceType} />
          <span className="inline-flex items-center gap-1 text-xs font-medium text-safe-700">
            <span aria-hidden="true">💾</span> {memory.localOnly ? 'Local SSD' : 'Synced'}
          </span>
        </div>

        <h1 className="mb-2 text-2xl font-bold leading-snug text-ink">{memory.title}</h1>
        <p className="mb-5 text-sm text-ink-muted">Captured {memory.capturedLabel}</p>

        {/* Source block */}
        <div className="mb-5 rounded-xl border border-slate-100 bg-slate-50 p-4">
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-muted">
            Source
          </div>
          <div className="text-sm font-medium text-ink">{source.title}</div>
          {source.domain && <div className="mt-1 text-xs text-ink-muted">{source.domain}</div>}
          {source.url ? (
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1 inline-flex items-center gap-1 break-all text-sm text-brand-700 hover:underline"
            >
              {source.url} <span aria-hidden="true">↗</span>
            </a>
          ) : (
            <div className="mt-1 text-sm text-ink-muted">No external URL</div>
          )}
        </div>

        <div className="mb-5 whitespace-pre-line text-sm leading-relaxed text-ink">
          {memory.content}
        </div>

        {/* AI summary — user-initiated, generated by the local Ollama model (Task 5.8) */}
        <section
          aria-label="AI summary"
          aria-busy={summarizing}
          className="mb-5 rounded-xl border border-slate-100 bg-slate-50 p-4"
        >
          <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-sm font-semibold text-ink">AI summary</h2>
            <button
              type="button"
              onClick={() => void handleGenerateSummary()}
              disabled={summarizing}
              className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {summarizing
                ? 'Generating…'
                : summaryData
                  ? 'Regenerate summary'
                  : 'Generate AI Summary'}
            </button>
          </div>
          {summarizing && (
            <p className="text-sm text-ink-muted" role="status" aria-live="polite">
              Asking the local model to summarize this memory — this can take a moment…
            </p>
          )}
          {summaryError && (
            <p role="alert" className="mb-2 text-sm text-red-700">
              {summaryError}
            </p>
          )}
          {summaryData && (
            <>
              <p className="whitespace-pre-line text-sm leading-6 text-ink">
                {summaryData.summary}
              </p>
              <p className="mt-3 border-t border-slate-200 pt-3 text-xs text-ink-muted">
                Generated locally by <span className="font-mono">{summaryData.model}</span> —
                this memory’s text stays on this device.
              </p>
            </>
          )}
        </section>

        {/* Metadata */}
        <dl className="mb-6 grid grid-cols-2 gap-4 rounded-xl border border-slate-100 p-4 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-xs text-ink-muted">Captured</dt>
            <dd className="font-medium text-ink">{memory.capturedLabel}</dd>
          </div>
          <div>
            <dt className="text-xs text-ink-muted">Source type</dt>
            <dd className="font-medium capitalize text-ink">{memory.sourceType.replace('-', ' ')}</dd>
          </div>
          <div>
            <dt className="text-xs text-ink-muted">Extraction</dt>
            <dd className="font-medium text-ink">{memory.extractionStatus || '—'}</dd>
          </div>
          <div>
            <dt className="text-xs text-ink-muted">Capture type</dt>
            <dd className="font-medium text-ink">{memory.captureType || '—'}</dd>
          </div>
          <div>
            <dt className="text-xs text-ink-muted">Content hash</dt>
            <dd className="break-all font-mono text-xs text-ink">{memory.contentHash || 'Stored'}</dd>
          </div>
          <div className="col-span-2 sm:col-span-3">
            <dt className="mb-1 text-xs text-ink-muted">Tags</dt>
            <dd className="flex flex-wrap gap-1.5">
              {memory.tags.map((tag) => (
                <span key={tag} className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                  {tag}
                </span>
              ))}
            </dd>
          </div>
        </dl>

        {memory.selectedText && (
          <section className="mb-5 rounded-xl border border-slate-100 bg-slate-50 p-4">
            <h2 className="mb-2 text-sm font-semibold text-ink">Selected text</h2>
            <p className="whitespace-pre-line text-sm text-ink">{memory.selectedText}</p>
            {memory.surroundingContext && (
              <p className="mt-3 border-t border-slate-200 pt-3 text-sm text-ink-muted">
                {memory.surroundingContext}
              </p>
            )}
          </section>
        )}

        {Object.keys(source.metadata).length > 0 && (
          <details className="mb-5 rounded-xl border border-slate-100 p-4">
            <summary className="cursor-pointer text-sm font-semibold text-ink">Source metadata</summary>
            <pre className="mt-3 overflow-x-auto whitespace-pre-wrap text-xs text-ink-muted">
              {JSON.stringify(source.metadata, null, 2)}
            </pre>
          </details>
        )}

        {error && <p role="alert" className="mb-4 text-sm text-red-700">{error}</p>}

        {/* Delete */}
        {confirming ? (
          <div className="rounded-xl border border-red-100 bg-red-50 p-4">
            <p className="mb-3 text-sm text-red-700">
              Delete “{memory.title}”? This removes it from local storage and cannot be undone.
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => void handleDelete()}
                disabled={deleting}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
              >
                {deleting ? 'Deleting…' : 'Yes, delete'}
              </button>
              <button
                type="button"
                onClick={() => setConfirming(false)}
                className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-ink hover:bg-slate-50"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            className="rounded-lg border border-red-200 bg-white px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50"
          >
            Delete memory
          </button>
        )}
      </article>
    </div>
  );
}
