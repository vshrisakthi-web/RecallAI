import { useState } from 'react';
import { ErrorState, LoadingState } from '../components/UIStates';
import { approveWorkflow, runWorkflow } from '../lib/workflowApi';
import type { ApprovalResult, TaskDraft, WorkflowRunResult } from '../lib/workflowApi';

/**
 * Workflow Review — the Module 8 approval surface.
 *
 * A user submits a question; the agent harness routes it, retrieves evidence,
 * analyzes it, and (for task objectives) drafts an evidence-backed checklist.
 * When drafts are returned the run is `awaiting_approval` — nothing is saved.
 *
 * This screen renders the proposed drafts and their supporting evidence and
 * lets the user make an explicit decision: Approve or Reject. Only that
 * explicit action calls the approval endpoint, which is the only thing that
 * persists tasks. Text returned by the model is shown to the user but is
 * never treated as approval.
 */

const PRIORITY_LABEL: Record<TaskDraft['priority'], string> = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
};

const KIND_LABEL: Record<TaskDraft['kind'], string> = {
  outstanding: 'Outstanding',
  recommended: 'Recommended',
};

function evidenceFor(sourceIds: string[], evidence: WorkflowRunResult['evidence']) {
  return evidence.filter((item) => sourceIds.includes(item.chunk_id));
}

export default function WorkflowReview() {
  const [question, setQuestion] = useState('');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<WorkflowRunResult | null>(null);
  const [approval, setApproval] = useState<ApprovalResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [deciding, setDeciding] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!question.trim() || running) return;
    setRunning(true);
    setError(null);
    setNotice(null);
    setApproval(null);
    setResult(null);
    try {
      const run = await runWorkflow(question.trim());
      setResult(run);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The workflow could not run.');
    } finally {
      setRunning(false);
    }
  }

  async function onDecide(decision: 'approve' | 'reject') {
    if (!result || deciding) return;
    setDeciding(true);
    setError(null);
    setNotice(null);
    try {
      const outcome = await approveWorkflow(result.run_id, decision);
      setApproval(outcome);
      setResult({ ...result, status: outcome.status });
      setNotice(
        outcome.status === 'completed'
          ? `Saved ${outcome.persisted_task_ids.length} task${outcome.persisted_task_ids.length === 1 ? '' : 's'}.`
          : 'Drafts rejected — nothing was saved.',
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The decision could not be recorded.');
    } finally {
      setDeciding(false);
    }
  }

  const awaiting = result?.status === 'awaiting_approval' && !approval;
  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <header>
        <h1 className="text-xl font-semibold text-ink">Workflow review</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Ask a question, review the evidence-backed task drafts, and approve or reject them.
          Nothing is saved until you approve.
        </p>
      </header>

      <form onSubmit={onSubmit} className="flex gap-2">
        <input
          type="text"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="e.g. create tasks from my RAG notes"
          aria-label="Workflow question"
          className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={running || !question.trim()}
          className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {running ? 'Running…' : 'Run'}
        </button>
      </form>

      {running && <LoadingState label="Retrieving evidence and drafting tasks…" />}
      {error && <ErrorState message={error} />}
      {notice && (
        <div role="status" className="rounded-lg border border-safe-100 bg-safe-50 p-3 text-sm text-safe-700">
          {notice}
        </div>
      )}

      {result && !running && (
        <section className="space-y-4" aria-label="Workflow result">
          {result.clarification && (
            <p className="rounded-lg border border-slate-100 bg-surface p-3 text-sm text-ink-muted">
              {result.clarification}
            </p>
          )}

          {result.errors.length > 0 && (
            <ul className="space-y-1" aria-label="Workflow errors">
              {result.errors.map((item, index) => (
                <li
                  key={`${item.stage}-${index}`}
                  className="rounded-lg border border-red-100 bg-red-50 p-3 text-sm text-red-700"
                >
                  {item.message}
                </li>
              ))}
            </ul>
          )}

          {result.task_drafts.length > 0 && (
            <div className="space-y-3" aria-label="Proposed task drafts">
              <h2 className="text-base font-semibold text-ink">Proposed tasks</h2>
              {result.task_drafts.map((draft, index) => {
                const refs = evidenceFor(draft.source_ids, result.evidence);
                return (
                  <article
                    key={index}
                    className="rounded-2xl border border-slate-100 bg-surface p-4 shadow-card"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <h3 className="text-sm font-semibold text-ink">{draft.title}</h3>
                      <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-ink-muted">
                        {KIND_LABEL[draft.kind]} · {PRIORITY_LABEL[draft.priority]}
                      </span>
                    </div>
                    <p className="mt-1 text-sm text-ink-muted">{draft.description}</p>
                    {refs.length > 0 && (
                      <ul className="mt-2 space-y-1" aria-label="Supporting evidence">
                        {refs.map((ev) => (
                          <li key={ev.chunk_id} className="rounded-lg bg-slate-50 p-2 text-xs text-ink-muted">
                            <span className="font-medium text-ink">{ev.source_title || 'Stored memory'}</span>
                            {': '}
                            {ev.passage}
                          </li>
                        ))}
                      </ul>
                    )}
                  </article>
                );
              })}
            </div>
          )}

          {awaiting && (
            <div className="flex gap-2" aria-label="Approval actions">
              <button
                type="button"
                onClick={() => onDecide('approve')}
                disabled={deciding}
                className="rounded-lg bg-safe-600 px-4 py-2 text-sm font-medium text-white hover:bg-safe-700 disabled:opacity-50"
              >
                {deciding ? 'Saving…' : 'Approve & save'}
              </button>
              <button
                type="button"
                onClick={() => onDecide('reject')}
                disabled={deciding}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-ink hover:bg-slate-50 disabled:opacity-50"
              >
                Reject
              </button>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

