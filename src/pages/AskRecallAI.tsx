import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { EmptyState, ErrorState } from '../components/UIStates';
import VoiceInput from '../components/VoiceInput';
import { askRecallAi } from '../lib/memoriesApi';
import type { AskEvidence, AskResult, RetrievalConfidence } from '../lib/memoriesApi';
import { suggestedQuestions } from '../data/mockData';

/**
 * Ask RecallAI — grounded retrieval over locally stored memories.
 *
 * Important: this screen shows **evidence, not generated answers**. The backend
 * retrieves passages and ranks them; it does not write prose. That is deliberate
 * — a privacy-first assistant must not present a guess as a confident answer,
 * so the UI shows exactly which stored passages matched and how strongly.
 *
 * Four distinct states are rendered, because they mean different things:
 *   loading — a request is in flight
 *   error   — the request failed (backend down, model unavailable)
 *   empty   — the search succeeded but nothing matched (confidence "none")
 *   results — evidence was found (confidence "weak" or "strong")
 */
interface Turn {
  id: string;
  question: string;
  result?: AskResult;
}

const CONFIDENCE_LABEL: Record<RetrievalConfidence, { text: string; className: string }> = {
  none: {
    text: 'No matching memories',
    className: 'bg-slate-100 text-ink-muted',
  },
  weak: {
    text: 'Weak evidence',
    className: 'bg-warn-100 text-warn-700',
  },
  strong: {
    text: 'Strong evidence',
    className: 'bg-safe-100 text-safe-700',
  },
};

function formatTimestamp(value?: string | null): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? null
    : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(parsed);
}

function EvidenceCard({ item, index }: { item: AskEvidence; index: number }) {
  const captured = formatTimestamp(item.captured_at);
  const title = item.source_title || item.domain || item.source_type || 'Stored memory';
  const percent = Math.round(Math.max(0, Math.min(1, item.similarity)) * 100);

  return (
    <div className="rounded-2xl border border-slate-100 bg-surface p-4 shadow-card">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span
          aria-hidden="true"
          className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-brand-100 text-xs font-semibold text-brand-700"
        >
          {index + 1}
        </span>
        <span className="text-sm font-semibold text-ink">{title}</span>
        {item.domain && item.source_title && (
          <span className="text-xs text-ink-muted">• {item.domain}</span>
        )}
      </div>

      <p className="whitespace-pre-line text-sm leading-relaxed text-ink">{item.passage}</p>

      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-slate-100 pt-3 text-xs text-ink-muted">
        {captured && <span>Captured {captured}</span>}
        {item.similarity > 0 && (
          <span data-testid="evidence-similarity">{percent}% match</span>
        )}
        {item.keyword_rank != null && <span>keyword #{item.keyword_rank}</span>}
        {item.matched_by.length > 0 && <span>via {item.matched_by.join(' + ')}</span>}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
        <Link
          to={`/memories/${encodeURIComponent(item.memory_id)}`}
          className="text-brand-700 hover:underline"
        >
          Open memory
        </Link>
        {item.source_url && (
          <a
            href={item.source_url}
            target="_blank"
            rel="noreferrer noopener"
            className="text-brand-700 hover:underline"
          >
            View source
          </a>
        )}
      </div>
    </div>
  );
}

/**
 * Browser-native text-to-speech using the Web Speech API.
 * Provides accessible play/pause/stop controls for reading answer text aloud.
 */
function SpeakerControls({
  text,
  onPlayStart,
  onPlayEnd,
}: {
  text: string;
  onPlayStart?: () => void;
  onPlayEnd?: () => void;
}) {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const ttsSupported = typeof window !== 'undefined' && 'speechSynthesis' in window;

  // Clean up on unmount
  useEffect(() => {
    return () => {
      if (ttsSupported) {
        window.speechSynthesis.cancel();
      }
    };
  }, [ttsSupported]);

  const handlePlay = () => {
    if (!text.trim() || !ttsSupported) return;

    // Cancel any ongoing speech to prevent overlap
    window.speechSynthesis.cancel();
    setIsPaused(false);

    const utterance = new SpeechSynthesisUtterance(text);
    utteranceRef.current = utterance;

    utterance.onstart = () => {
      setIsSpeaking(true);
      setIsPaused(false);
      onPlayStart?.();
    };

    utterance.onend = () => {
      setIsSpeaking(false);
      setIsPaused(false);
      onPlayEnd?.();
    };

    utterance.onerror = () => {
      setIsSpeaking(false);
      setIsPaused(false);
      onPlayEnd?.();
    };

    window.speechSynthesis.speak(utterance);
  };

  const handleStop = () => {
    if (!isSpeaking || !ttsSupported) return;
    window.speechSynthesis.cancel();
    setIsSpeaking(false);
    setIsPaused(false);
    onPlayEnd?.();
  };

  const handlePause = () => {
    if (!isSpeaking || isPaused || !ttsSupported) return;
    window.speechSynthesis.pause();
    setIsPaused(true);
  };

  const handleResume = () => {
    if (!isPaused || !ttsSupported) return;
    window.speechSynthesis.resume();
    setIsPaused(false);
  };

  const handlePrimary = isSpeaking ? (isPaused ? handleResume : handlePause) : handlePlay;
  const primaryAria = isSpeaking
    ? isPaused
      ? 'Resume playback'
      : 'Pause playback'
    : 'Play answer aloud';

  return (
    <div className="flex items-center gap-2 mt-2 text-sm" data-testid="tts-controls">
      <button
        type="button"
        onClick={handlePrimary}
        disabled={!ttsSupported || !text.trim()}
        aria-label={primaryAria}
        className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-ink hover:border-brand-200 hover:text-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-100 disabled:cursor-not-allowed disabled:opacity-50"
        data-testid="tts-play-pause"
      >
        {isSpeaking ? (isPaused ? '▶️' : '⏸️') : '🔊'}
        <span className="sr-only">
          {isSpeaking ? (isPaused ? 'Resume' : 'Pause') : 'Play'}
        </span>
      </button>

      <button
        type="button"
        onClick={handleStop}
        disabled={!isSpeaking || !ttsSupported}
        aria-label="Stop playback"
        className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-ink hover:border-red-200 hover:text-red-700 focus:outline-none focus:ring-2 focus:ring-brand-100 disabled:cursor-not-allowed disabled:opacity-50"
        data-testid="tts-stop"
      >
        ⏹️
        <span className="sr-only">Stop</span>
      </button>

      {/* Live region for screen reader announcements */}
      <p
        role="status"
        aria-live="polite"
        className="sr-only"
        data-testid="tts-status"
      >
        {isSpeaking
          ? isPaused
            ? 'Playback paused'
            : 'Reading answer aloud'
          : 'Ready to play answer'}
      </p>
    </div>
  );
}

export default function AskRecallAI() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [failedQuestion, setFailedQuestion] = useState('');

  // Aborts the in-flight request on unmount or when a newer question is asked,
  // so a stale response can never overwrite a newer one.
  const inFlight = useRef<AbortController | null>(null);
  useEffect(() => () => inFlight.current?.abort(), []);

  // Clean up any ongoing speech on unmount
  useEffect(() => {
    return () => {
      if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  /**
   * Builds speakable text from a turn's question and result.
   * Excludes UI-only elements and focuses on meaningful content.
   */
  function buildSpeakableText(turn: Turn): string {
    if (!turn.result) return '';

    const parts: string[] = [];
    parts.push(turn.question);

    const confidence = turn.result.confidence ?? 'none';
    if (confidence !== 'none') {
      parts.push(CONFIDENCE_LABEL[confidence].text);
    }

    if (turn.result.temporal_expression) {
      parts.push(`filtered to ${turn.result.temporal_expression}`);
    }

    if (turn.result.evidence.length > 0) {
      parts.push(...turn.result.evidence.map((ev) => ev.passage).filter(Boolean));
    } else {
      parts.push('No stored memory matched this question.');
    }

    return parts.filter(Boolean).join('. ');
  }

  const ask = (question: string) => {
    const q = question.trim();
    if (!q || loading) return; // guard against duplicate submissions
    inFlight.current?.abort();
    const controller = new AbortController();
    inFlight.current = controller;

    setError(null);
    setLoading(true);
    setTurns((prev) => [...prev, { id: `turn-${Date.now()}`, question: q }]);
    setInput('');

    askRecallAi({ question: q }, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        setTurns((prev) =>
          prev.map((t) =>
            t.question === q && !t.result ? { ...t, result } : t,
          ),
        );
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setFailedQuestion(q);
        setError(err instanceof Error ? err.message : 'Retrieval failed. Please try again.');
        // Drop the optimistic question bubble; the error explains the failure.
        setTurns((prev) => prev.filter((t) => t.question !== q || t.result));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
  };

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col">
      <div className="mb-4">
        <h1 className="text-2xl font-bold text-ink">Ask RecallAI</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Ask questions about your locally stored memories. Runs 100% on-device — RecallAI
          retrieves the passages that match and shows the evidence behind them.
        </p>
      </div>

      {/* Conversation */}
      <div className="mb-4 flex-1 space-y-4" data-testid="ask-conversation">
        {turns.length === 0 ? (
          <EmptyState
            title="Ask anything about your memories"
            description="RecallAI searches your stored memories and shows the passages that match."
          />
        ) : (
          turns.map((turn) => {
            const confidence = turn.result?.confidence ?? 'none';
            const badge = CONFIDENCE_LABEL[confidence];
            return (
              <div key={turn.id} className="space-y-3">
                <div className="flex justify-end">
                  <p className="max-w-[80%] rounded-2xl rounded-br-sm bg-brand-700 px-4 py-2 text-sm text-white">
                    {turn.question}
                  </p>
                </div>

                {turn.result && (
                  <div data-testid="ask-result">
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <span
                        data-testid="confidence-badge"
                        className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ${badge.className}`}
                      >
                        {badge.text}
                      </span>
                      {turn.result.temporal_expression && (
                        <span className="text-xs text-ink-muted">
                          filtered to “{turn.result.temporal_expression}”
                        </span>
                      )}
                      <span className="text-xs text-ink-muted">
                        {turn.result.evidence.length} passage
                        {turn.result.evidence.length === 1 ? '' : 's'} from{' '}
                        {turn.result.candidates_considered} candidate
                        {turn.result.candidates_considered === 1 ? '' : 's'}
                      </span>
                    </div>

                    {turn.result.evidence.length === 0 ? (
                      <div className="rounded-2xl border border-dashed border-slate-200 bg-surface p-4">
                        <p className="text-sm text-ink" data-testid="no-evidence">
                          No stored memory matched this question.
                        </p>
                        <p className="mt-1 text-xs text-ink-muted">
                          This is a successful search that found nothing — not an error. Try
                          different words, or index more memories.
                        </p>
                      </div>
                    ) : (
                      turn.result.evidence.map((item, index) => (
                        <div key={item.chunk_id} className="mb-3">
                          <EvidenceCard item={item} index={index} />
                        </div>
                      ))
                    )}
                                    </div>
                )}

                {/* Speaker controls for reading the answer aloud */}
                {turn.result && (
                  <div className="mt-2 flex items-center gap-3 text-sm">
                    <SpeakerControls
                      text={buildSpeakableText(turn)}
                      onPlayStart={() => {}}
                      onPlayEnd={() => {}}
                    />
                  </div>
                )}
              </div>
            );
          })
        )}

        {loading && (
          <div
            data-testid="ask-loading"
            className="flex items-center gap-2 text-sm text-ink-muted"
            role="status"
          >
            <span
              aria-hidden="true"
              className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-brand-100 border-t-brand-600"
            />
            Searching your memories…
          </div>
        )}

        {error && (
          <ErrorState
            message={error}
            onRetry={() => {
              setError(null);
              ask(failedQuestion || input || suggestedQuestions[0]);
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
              disabled={loading}
              className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs text-ink-muted hover:border-brand-200 hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
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
            {loading ? 'Searching…' : 'Ask'}
          </button>
        </div>

        {/*
         * Voice input (Task 81). It sits beside — never instead of — the text box:
         * a transcript is placed into the same `input` state, so reviewing and
         * editing it is automatic and the existing submit path is unchanged.
         */}
        <div className="mt-3 border-t border-slate-100 pt-3">
          <VoiceInput
            disabled={loading}
            onTranscript={(transcript) => {
              // Fill, do not submit: the user still presses Ask, so voice input
              // and typed input are literally the same code path from here on.
              setInput(transcript);
            }}
          />
        </div>

        <p className="mt-2 text-xs text-ink-muted">
          RecallAI retrieves evidence from your local memories. It does not generate answers,
          so it will never guess.
        </p>
      </form>
    </div>
  );
}
