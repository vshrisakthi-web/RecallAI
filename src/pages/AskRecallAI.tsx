import { useState } from 'react';
import { Link } from 'react-router-dom';
import { EmptyState, ErrorState } from '../components/UIStates';
import { initialConversation, mockAsk, suggestedQuestions } from '../data/mockData';
import { useMemories } from '../state/MemoriesContext';
import type { ChatTurn } from '../data/types';

/**
 * Ask RecallAI — the AI Q&A interface. Every answer is MOCK and is rendered with
 * a visible "Mock answer" badge. There is no live AI backend in Module 1.
 */
export default function AskRecallAI() {
  const { memories } = useMemories();
  const [turns, setTurns] = useState<ChatTurn[]>(initialConversation);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const ask = (question: string) => {
    const q = question.trim();
    if (!q || loading) return;
    setError(false);
    setLoading(true);
    // Simulate a mock "thinking" delay. No network, no real model.
    window.setTimeout(() => {
      setTurns((prev) => [...prev, mockAsk(q, memories)]);
      setInput('');
      setLoading(false);
    }, 400);
  };

  const simulateError = () => {
    setLoading(true);
    window.setTimeout(() => {
      setLoading(false);
      setError(true);
    }, 400);
  };

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col">
      <div className="mb-4">
        <h1 className="text-2xl font-bold text-ink">Ask RecallAI</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Ask questions about your locally stored memories. Runs 100% on-device — answers
          are simulated with mock data.
        </p>
      </div>

      {/* Conversation */}
      <div className="mb-4 flex-1 space-y-4">
        {turns.length === 0 ? (
          <EmptyState
            title="Ask anything about your memories"
            description="Try one of the suggested questions to get started."
          />
        ) : (
          turns.map((turn) => (
            <div key={turn.id} className="space-y-3">
              {/* User question */}
              <div className="flex justify-end">
                <p className="max-w-[80%] rounded-2xl rounded-br-sm bg-brand-700 px-4 py-2 text-sm text-white">
                  {turn.question}
                </p>
              </div>
              {/* Mock answer card */}
              <div className="rounded-2xl border border-slate-100 bg-surface p-4 shadow-card">
                <div className="mb-2 flex items-center gap-2">
                  <span
                    data-testid="mock-answer-badge"
                    className="inline-flex items-center gap-1 rounded-full bg-warn-100 px-2.5 py-0.5 text-xs font-semibold text-warn-700"
                  >
                    <span aria-hidden="true">⚠️</span> Mock answer
                  </span>
                  <span className="text-xs text-ink-muted">Not a real AI response</span>
                </div>
                <p className="whitespace-pre-line text-sm leading-relaxed text-ink">
                  {turn.answer}
                </p>
                {turn.references.length > 0 && (
                  <div className="mt-3 border-t border-slate-100 pt-3">
                    <div className="mb-1.5 text-xs font-semibold text-ink-muted">Sources</div>
                    <ul className="space-y-1">
                      {turn.references.map((ref) => (
                        <li key={ref.memoryId}>
                          <Link
                            to={`/memory/${ref.memoryId}`}
                            className="inline-flex items-center gap-1 text-sm text-brand-700 hover:underline"
                          >
                            <span aria-hidden="true">📄</span> {ref.title}
                            <span className="text-xs text-ink-muted">• {ref.sourceName}</span>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          ))
        )}

        {loading && (
          <div className="flex items-center gap-2 text-sm text-ink-muted" role="status">
            <span
              aria-hidden="true"
              className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-brand-100 border-t-brand-600"
            />
            RecallAI is thinking (mock)…
          </div>
        )}

        {error && (
          <ErrorState
            message="The mock assistant failed to respond. Try again."
            onRetry={() => {
              setError(false);
              ask(input || suggestedQuestions[0]);
            }}
          />
        )}
      </div>

      {/* Suggested questions */}
      {turns.length === 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {suggestedQuestions.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => ask(q)}
              className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs text-ink-muted hover:border-brand-200 hover:text-ink"
            >
              {q}
            </button>
          ))}
        </div>
      )}

      {/* Composer */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(input);
        }}
        className="rounded-2xl border border-slate-100 bg-surface p-3 shadow-card"
      >
        <div className="flex gap-2">
          <label htmlFor="ask-input" className="sr-only">
            Ask a question
          </label>
          <input
            id="ask-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about your memories…"
            className="flex-1 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm text-ink placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
          />
          <button
            type="submit"
            disabled={loading || input.trim().length === 0}
            className="rounded-xl bg-brand-700 px-4 py-2.5 text-sm font-medium text-white hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Ask
          </button>
        </div>
        <div className="mt-2 flex justify-end">
          <button
            type="button"
            onClick={simulateError}
            className="text-xs text-ink-muted hover:text-red-600 hover:underline"
          >
            Simulate error
          </button>
        </div>
      </form>
    </div>
  );
}
