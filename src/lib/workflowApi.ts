/// <reference types="vite/client" />

/**
 * Client for the Module 8 agent-harness workflow + approval API.
 *
 * Two calls, mirroring the backend boundary:
 *   - `runWorkflow` submits a question and returns a structured run result.
 *     When the objective is task creation it returns drafts in
 *     `awaiting_approval` — drafts are NOT saved yet.
 *   - `approveWorkflow` submits an explicit user decision (approve/edit/reject)
 *     for a run awaiting approval. This is the ONLY call that persists tasks.
 *
 * Approval is a real user action (a button press that calls this function).
 * Nothing the model returns is ever treated as approval.
 */

const apiBase = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1').replace(/\/$/, '');

export type WorkflowObjective = 'search' | 'summarize' | 'analyze_learning' | 'create_tasks';
export type RunStatus =
  | 'pending'
  | 'running'
  | 'awaiting_approval'
  | 'completed'
  | 'failed'
  | 'rejected'
  | 'cancelled';
export type TaskKind = 'outstanding' | 'recommended';
export type TaskPriority = 'high' | 'medium' | 'low';

export interface WorkflowFinding {
  statement: string;
  evidence_refs: string[];
}

export interface WorkflowEvidence {
  chunk_id: string;
  memory_id: string;
  source_title?: string | null;
  source_url?: string | null;
  passage: string;
}

export interface TaskDraft {
  title: string;
  description: string;
  priority: TaskPriority;
  source_ids: string[];
  kind: TaskKind;
  status: 'draft';
}

export interface WorkflowErrorItem {
  stage: string;
  category: string;
  message: string;
}

export interface WorkflowRunResult {
  run_id: string;
  objective: WorkflowObjective | null;
  status: RunStatus;
  clarification: string | null;
  findings: WorkflowFinding[];
  evidence: WorkflowEvidence[];
  task_drafts: TaskDraft[];
  errors: WorkflowErrorItem[];
}

export interface ApprovalResult {
  run_id: string;
  status: RunStatus;
  persisted_task_ids: string[];
}

export type ApprovalDecision = 'approve' | 'edit' | 'reject';

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBase}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...init.headers },
    });
  } catch (error) {
    throw new Error(error instanceof Error ? error.message : 'The backend is unavailable.');
  }
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { detail?: string; error?: { message?: string } }
      | null;
    throw new Error(payload?.detail || payload?.error?.message || `Request failed (${response.status}).`);
  }
  return response.json() as Promise<T>;
}

export async function runWorkflow(question: string, signal?: AbortSignal): Promise<WorkflowRunResult> {
  return request<WorkflowRunResult>('/workflow', {
    method: 'POST',
    body: JSON.stringify({ question }),
    signal,
  });
}

export async function approveWorkflow(
  runId: string,
  decision: ApprovalDecision,
  editedDrafts?: { tasks: TaskDraft[] },
  signal?: AbortSignal,
): Promise<ApprovalResult> {
  const body: { decision: ApprovalDecision; edited_drafts?: { tasks: TaskDraft[] } } = { decision };
  if (decision === 'edit' && editedDrafts) body.edited_drafts = editedDrafts;
  return request<ApprovalResult>(`/workflow/${encodeURIComponent(runId)}/approve`, {
    method: 'POST',
    body: JSON.stringify(body),
    signal,
  });
}
