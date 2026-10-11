import { useState } from 'react';
import { Link } from 'react-router-dom';
import { currentPageContext, mockAsk } from '../data/mockData';
import { useMemories } from '../state/MemoriesContext';

/**
 * Companion side panel — a narrow ~380px panel docked beside the page. Shows the
 * CURRENT PAGE CONTEXT (visually distinct from stored memories), contextual chat
 * with source references + "Mock answer" badges, and related memories.
 *
 * Isolated preview route (/panel). In a real build this becomes the Manifest V3
 * side-panel entry point. Answers are mock — no live AI backend.
 */
export default function CompanionSidePanel() {
  const { memories } = useMemories();
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<null | { text: string; refs: string[] }>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const related = memories.slice(0, 3);

  const ask = () => {
    const q = question.trim();
    if (!q || loading) return;
    setError(false);
    setLoading(true);
    window.setTimeout(() => {
      const turn = mockAsk(q, memories);
      setAnswer({ text: turn.answer, refs: turn.references.map((r) => r.title) });
      setQuestion('');
      setLoading(false);
    }, 400);
  };

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
          {/* Chat / answer */}
          {answer === null && !loading && !error && (
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
              Thinking (mock)…
            </div>
          )}

          {error && (
            <div
              role="alert"
              className="rounded-xl border border-red-100 bg-red-50 p-3 text-sm text-red-600"
            >
              The mock assistant failed.{' '}
              <button
                type="button"
                onClick={() => setError(false)}
                className="font-medium underline"
              >
                Dismiss
              </button>
            </div>
          )}

          {answer && (
            <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
              <span
                data-testid="panel-mock-badge"
                className="mb-2 inline-flex items-center gap-1 rounded-full bg-warn-100 px-2 py-0.5 text-xs font-semibold text-warn-700"
              >
                ⚠️ Mock answer
              </span>
              <p className="whitespace-pre-line text-sm text-ink">{answer.text}</p>
              {answer.refs.length > 0 && (
                <div className="mt-2 border-t border-slate-200 pt-2">
                  <div className="mb-1 text-xs font-semibold text-ink-muted">Source references</div>
                  <ul className="space-y-0.5 text-xs text-brand-700">
                    {answer.refs.map((r) => (
                      <li key={r} className="truncate">
                        📄 {r}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* Related memories */}
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
              Related memories
            </div>
            {related.length === 0 ? (
              <p className="text-xs text-ink-muted">No related memories yet.</p>
            ) : (
              <ul className="space-y-1.5">
                {related.map((m) => (
                  <li key={m.id}>
                    <Link
                      to={`/memory/${m.id}`}
                      className="block truncate rounded-lg border border-slate-100 px-2.5 py-2 text-xs text-ink hover:border-brand-200 hover:bg-slate-50"
                    >
                      {m.sourceName} • {m.title}
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
              className="rounded-lg bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
            >
              Ask
            </button>
          </div>
          <div className="mt-2 flex justify-between text-xs">
            <button
              type="button"
              onClick={() => {
                setLoading(true);
                window.setTimeout(() => {
                  setLoading(false);
                  setError(true);
                }, 300);
              }}
              className="text-ink-muted hover:text-red-600 hover:underline"
            >
              Simulate error
            </button>
            <Link to="/ask" className="text-brand-700 hover:underline">
              Open full Ask →
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
