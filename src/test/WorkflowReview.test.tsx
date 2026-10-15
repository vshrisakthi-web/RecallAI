import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import WorkflowReview from '../pages/WorkflowReview';
import { approveWorkflow, runWorkflow } from '../lib/workflowApi';
import type { WorkflowRunResult } from '../lib/workflowApi';

vi.mock('../lib/workflowApi', () => ({
  runWorkflow: vi.fn(),
  approveWorkflow: vi.fn(),
}));

const mockedRun = vi.mocked(runWorkflow);
const mockedApprove = vi.mocked(approveWorkflow);

function awaitingResult(overrides: Partial<WorkflowRunResult> = {}): WorkflowRunResult {
  return {
    run_id: 'run_abc',
    objective: 'create_tasks',
    status: 'awaiting_approval',
    clarification: null,
    findings: [{ statement: 'Notes cover RAG embeddings.', evidence_refs: ['chk_1'] }],
    evidence: [
      {
        chunk_id: 'chk_1',
        memory_id: 'mem_1',
        source_title: 'RAG embeddings',
        source_url: null,
        passage: 'RAG retrieval uses embeddings and vector search.',
      },
    ],
    task_drafts: [
      {
        title: 'Review RAG embeddings notes',
        description: 'Re-read the saved RAG notes.',
        priority: 'high',
        source_ids: ['chk_1'],
        kind: 'outstanding',
        status: 'draft',
      },
    ],
    errors: [],
    ...overrides,
  };
}

function renderReview() {
  return render(
    <MemoryRouter>
      <WorkflowReview />
    </MemoryRouter>,
  );
}

describe('Workflow Review (approval boundary)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders proposed drafts with supporting evidence and no approval yet', async () => {
    mockedRun.mockResolvedValue(awaitingResult());
    const user = userEvent.setup();
    renderReview();

    await user.type(screen.getByLabelText('Workflow question'), 'create tasks from my RAG notes');
    await user.click(screen.getByRole('button', { name: 'Run' }));

    expect(await screen.findByText('Review RAG embeddings notes')).toBeInTheDocument();
    expect(screen.getByText(/RAG retrieval uses embeddings/)).toBeInTheDocument();
    // No persistence happened by merely rendering drafts.
    expect(mockedApprove).not.toHaveBeenCalled();
  });

  it('approve calls the endpoint with an explicit decision and shows success', async () => {
    mockedRun.mockResolvedValue(awaitingResult());
    mockedApprove.mockResolvedValue({ run_id: 'run_abc', status: 'completed', persisted_task_ids: ['task_1'] });
    const user = userEvent.setup();
    renderReview();

    await user.type(screen.getByLabelText('Workflow question'), 'create tasks from my RAG notes');
    await user.click(screen.getByRole('button', { name: 'Run' }));
    const approve = await screen.findByRole('button', { name: /Approve & save/i });
    await user.click(approve);

    await waitFor(() =>
      expect(mockedApprove).toHaveBeenCalledWith('run_abc', 'approve'),
    );
    expect(await screen.findByText(/Saved 1 task/)).toBeInTheDocument();
  });

  it('reject calls the endpoint and reports nothing was saved', async () => {
    mockedRun.mockResolvedValue(awaitingResult());
    mockedApprove.mockResolvedValue({ run_id: 'run_abc', status: 'rejected', persisted_task_ids: [] });
    const user = userEvent.setup();
    renderReview();

    await user.type(screen.getByLabelText('Workflow question'), 'create tasks from my RAG notes');
    await user.click(screen.getByRole('button', { name: 'Run' }));
    const reject = await screen.findByRole('button', { name: 'Reject' });
    await user.click(reject);

    await waitFor(() =>
      expect(mockedApprove).toHaveBeenCalledWith('run_abc', 'reject'),
    );
    expect(await screen.findByText(/nothing was saved/i)).toBeInTheDocument();
  });

  it('surfaces an approval error (e.g. validation/storage) as an error state', async () => {
    mockedRun.mockResolvedValue(awaitingResult());
    mockedApprove.mockRejectedValue(new Error('The approved tasks could not be saved right now.'));
    const user = userEvent.setup();
    renderReview();

    await user.type(screen.getByLabelText('Workflow question'), 'create tasks from my RAG notes');
    await user.click(screen.getByRole('button', { name: 'Run' }));
    const approve = await screen.findByRole('button', { name: /Approve & save/i });
    await user.click(approve);

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not be saved/i);
  });

  it('does not approve based on rendered text — only the button triggers it', async () => {
    mockedRun.mockResolvedValue(awaitingResult());
    const user = userEvent.setup();
    renderReview();

    await user.type(screen.getByLabelText('Workflow question'), 'create tasks from my RAG notes');
    await user.click(screen.getByRole('button', { name: 'Run' }));
    await screen.findByText('Review RAG embeddings notes');

    // Draft text (a statement) is visible but never an approval action.
    expect(mockedApprove).not.toHaveBeenCalled();
  });
});
