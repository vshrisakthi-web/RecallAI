import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import SourceBadge from '../components/SourceBadge';
import { ErrorState, LoadingState } from '../components/UIStates';
import { useMemories } from '../state/MemoriesContext';

/**
 * Memory Detail — full view of a single memory: title, content, original source
 * + clickable link, capture date, metadata, and a delete action (with a
 * confirmation step). Returns to the timeline after deletion.
 *
 * Design note: no Stitch export exists for this screen (Task 1.8 pending), so it
 * is built from docs/interface-specification.md and matches the shared design system.
 */
export default function MemoryDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { getMemory, deleteMemory } = useMemories();
  const [loading, setLoading] = useState(true);
  const [confirming, setConfirming] = useState(false);

  // Simulate a brief load so the loading state is reachable/demonstrable.
  useEffect(() => {
    setLoading(true);
    const t = setTimeout(() => setLoading(false), 150);
    return () => clearTimeout(t);
  }, [id]);

  const memory = id ? getMemory(id) : undefined;

  if (loading) {
    return (
      <div className="mx-auto max-w-3xl">
        <LoadingState label="Loading memory…" />
      </div>
    );
  }

  if (!memory) {
    return (
      <div className="mx-auto max-w-3xl">
        <ErrorState
          message="This memory could not be found. It may have been deleted."
          onRetry={() => navigate('/timeline')}
        />
        <div className="mt-4 text-center">
          <Link to="/timeline" className="text-sm font-medium text-brand-700 hover:underline">
            ← Back to Timeline
          </Link>
        </div>
      </div>
    );
  }

  const handleDelete = () => {
    deleteMemory(memory.id);
    navigate('/timeline');
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
          <div className="text-sm font-medium text-ink">{memory.sourceName}</div>
          {memory.sourceUrl && !memory.sourceUrl.startsWith('file://') ? (
            <a
              href={memory.sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1 inline-flex items-center gap-1 break-all text-sm text-brand-700 hover:underline"
            >
              {memory.sourceUrl} <span aria-hidden="true">↗</span>
            </a>
          ) : (
            <div className="mt-1 text-sm text-ink-muted">{memory.sourceUrl || 'No link'}</div>
          )}
        </div>

        <div className="mb-5 whitespace-pre-line text-sm leading-relaxed text-ink">
          {memory.content}
        </div>

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
            <dd className="font-medium text-ink">{memory.extractNote || '—'}</dd>
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

        {/* Delete */}
        {confirming ? (
          <div className="rounded-xl border border-red-100 bg-red-50 p-4">
            <p className="mb-3 text-sm text-red-700">
              Delete “{memory.title}”? This removes it from local storage and cannot be undone.
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleDelete}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
              >
                Yes, delete
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
