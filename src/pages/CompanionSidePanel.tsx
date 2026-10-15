import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { currentPageContext } from '../data/mockData';
import { askRecallAi } from '../lib/memoriesApi';
import type { AskEvidence, AskResult, RetrievalConfidence } from '../lib/memoriesApi';

/**
 * Companion side panel — a narrow ~380px panel docked beside the page.
 *
 * Shows the CURRENT PAGE CONTEXT (visually distinct from stored memories) and
 * answers questions with **retrieved evidence**, not generated prose. The
 * backend does not write answers, so the panel never fabricates one: it shows
 * which stored passages matched and how strongly.
 *
 * Isolated preview route (/panel). In a real build this becomes the Manifest V3
 * side-panel entry point.
 */
const CONFIDENCE_LABEL: Record<RetrievalConfidence, { text: string; className: string }> = {
  none: { text: 'No matching memories', className: 'bg-slate-100 text-ink-muted' },
  weak: { text: 'Weak evidence', className: 'bg-warn-100 text-warn-700' },
  strong: { text: 'Strong evidence', className: 'bg-safe-100 text-safe-700' },
};

export default function CompanionSidePanel() {
  const [question, setQuestion] = useState('');
  const [result, setResult] = useState<AskResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Aborts the in-flight request so a stale response cannot overwrite a newer one.
  const inFlight = useRef<AbortController | null>(null);
  useEffect(() => () => inFlight.current?.abort(), []);

  const ask = () => {
    const q = question.trim();
    if (!q || loading) return; // guard against duplicate submissions
    inFlight.current?.abort();
    const controller = new AbortController();
    inFlight.current = controller;

    setError(null);
    setResult(null);
    setLoading(true);
    setQuestion('');

    askRecallAi({ question: q }, controller.signal)
      .then((answer) => {
        if (!controller.signal.aborted) setResult(answer);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : 'Retrieval failed. Please try again.');
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
  };

  const related = (result?.evidence ?? []).slice(0, 3);

  return (
    <div className="flex min-h-screen items-start justify-center bg-canvas p-6">
      <div className="flex w-[380px] flex-col overflow-hidden rounded-2xl border border-slate-100 bg-surface shadow-card">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
          <div className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand-600 text-white"
            >
              ↻
            </span>
            <span className="text-sm font-bold text-ink">RecallAI Companion</span>
          </div>
          <span className="text-xs text-ink-muted">🔒 Local</span>
        </div>

        {/* Current page context — distinct from stored memories */}
        <div className="border-b border-slate-100 bg-brand-50 px-4 py-3">
          <div className="mb-1 inline-flex items-center gap-1 rounded-full bg-brand-100 px-2 py-0.5 text-xs font-semibold text-brand-700">
            <span aria-hidden="true">🌐</span> Current page context
          </div>
          <div className="text-sm font-semibold text-ink">{currentPageContext.title}</div>
          <div className="text-xs text-ink-muted">{currentPageContext.domain}</div>
        </div>

        <div className="flex-1 space-y-4 px-4 py-4">
          {/* Retrieved evidence */}
          {result === null && !loading && !error && (
            <div className="rounded-xl border border-dashed border-slate-200 p-4 text-center">
              <p className="text-sm text-ink-muted">
                Ask a question about the current page or your stored memories.
              </p>
            </div>
          )}

          {loading && (
            <div className="flex items-center gap-2 text-sm text-ink-muted" role="status">
              <span
                aria-hidden="true"
                className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-brand-100 border-t-brand-600"
              />
              Searching your memories…
            </div>
          )}

          {error && (
            <div
              role="alert"
              className="rounded-xl border border-red-100 bg-red-50 p-3 text-sm text-red-600"
            >
              {error}{' '}
              <button
                type="button"
                onClick={() => setError(null)}
                className="font-medium underline"
              >
                Dismiss
              </button>
            </div>
          )}

          {result && (
            <div data-testid="panel-result">
              <span
                data-testid="panel-confidence-badge"
                className={`mb-2 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${
                  CONFIDENCE_LABEL[result.confidence].className
                }`}
              >
                {CONFIDENCE_LABEL[result.confidence].text}
              </span>

              {result.evidence.length === 0 ? (
                <p className="text-sm text-ink" data-testid="panel-no-evidence">
                  No stored memory matched this question.
                </p>
              ) : (
                <ul className="space-y-2" data-testid="panel-evidence">
                  {result.evidence.map((item: AskEvidence) => (
                    <li
                      key={item.chunk_id}
                      className="rounded-xl border border-slate-100 bg-slate-50 p-3"
                    >
                      <div className="mb-1 text-xs font-semibold text-ink">
                        {item.source_title || item.domain || 'Stored memory'}
                      </div>
                      <p className="whitespace-pre-line text-sm text-ink">{item.passage}</p>
                      <Link
                        to={`/memories/${encodeURIComponent(item.memory_id)}`}
                        className="mt-1 inline-block text-xs text-brand-700 hover:underline"
                      >
                        Open memory
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* Related memories — the passages this answer was built from */}
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
              Related memories
            </div>
            {related.length === 0 ? (
              <p className="text-xs text-ink-muted">No related memories yet.</p>
            ) : (
              <ul className="space-y-1.5" data-testid="panel-related">
                {related.map((m) => (
                  <li key={m.chunk_id}>
                    <Link
                      to={`/memories/${encodeURIComponent(m.memory_id)}`}
                      className="block truncate rounded-lg border border-slate-100 px-2.5 py-2 text-xs text-ink-muted hover:border-brand-200 hover:text-ink"
                    >
                      {m.source_title || m.domain || 'Stored memory'} •{' '}
                      {m.source_type || 'memory'}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* Composer */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            ask();
          }}
          className="border-t border-slate-100 p-3"
        >
          <div className="flex gap-2">
            <label htmlFor="panel-input" className="sr-only">
              Ask about the current page
            </label>
            <input
              id="panel-input"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask about this page…"
              className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
            />
            <button
              type="submit"
              disabled={loading || question.trim().length === 0}
              className="rounded-lg bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? 'Searching…' : 'Ask'}
            </button>
          </div>
          <p className="mt-2 text-xs text-ink-muted">
            Shows the stored passages that match — RecallAI does not generate answers.
          </p>
          <div className="mt-1 text-right">
            <Link to="/ask" className="text-xs text-brand-700 hover:underline">
              Open full Ask →
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
