import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom';
import MemoryDetail from '../pages/MemoryDetail';
import { deleteMemory, getMemory, summarizeMemory } from '../lib/memoriesApi';
import type { MemorySummary } from '../lib/memoriesApi';
import type { Memory } from '../data/types';

vi.mock('../lib/memoriesApi', () => ({
  deleteMemory: vi.fn(),
  getMemory: vi.fn(),
  summarizeMemory: vi.fn(),
}));

const memory: Memory = {
  id: 'saved-1',
  title: 'Saved browser memory',
  excerpt: 'Actual saved content',
  content: 'Actual saved content with useful detail.',
  sourceType: 'browser',
  sourceName: 'Example docs',
  sourceUrl: 'https://docs.example/page',
  capturedAt: '2026-10-10T08:00:00Z',
  capturedLabel: 'Oct 10, 2026, 8:00 AM',
  tags: [],
  localOnly: true,
  sourceId: 'source-1',
  domain: 'docs.example',
  extractionStatus: 'ok',
  contentHash: 'abc123',
};

const source = {
  id: 'source-1',
  source_type: 'browser',
  url: 'https://docs.example/page',
  domain: 'docs.example',
  title: 'Example docs',
  metadata: {},
  created_at: '2026-10-10T08:00:00Z',
  updated_at: '2026-10-10T08:00:00Z',
  memory_count: 1,
};

const memoryTwo: Memory = {
  ...memory,
  id: 'saved-2',
  title: 'Second saved memory',
  content: 'Different content for the second memory.',
  contentHash: 'def456',
};

const summaryFixture: MemorySummary = {
  memory_id: 'saved-1',
  summary: '• First bullet of the summary.\n• Second bullet of the summary.',
  model: 'llama3.2:1b',
};

function renderDetail(id: string) {
  return render(
    <MemoryRouter initialEntries={[`/memory/${id}`]}>
      <Routes>
        <Route path="/memory/:id" element={<MemoryDetail />} />
        <Route path="/timeline" element={<div>Timeline screen</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

/** Programmatic navigation between two memory details without a remount. */
function NavigationHelper({ to, label }: { to: string; label: string }) {
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => navigate(to)}>
      {label}
    </button>
  );
}

describe('Memory Detail', () => {
  beforeEach(() => {
    // Isolate mock call counts between tests (implementations are re-set below).
    vi.clearAllMocks();
    vi.mocked(getMemory).mockResolvedValue({ memory, source });
    vi.mocked(deleteMemory).mockResolvedValue();
    vi.mocked(summarizeMemory).mockResolvedValue(summaryFixture);
  });

  it('renders the memory content and a back link', async () => {
    renderDetail('saved-1');
    expect(await screen.findByRole('heading', { name: 'Saved browser memory' })).toBeInTheDocument();
    expect(screen.getByText('Actual saved content with useful detail.')).toBeInTheDocument();
    expect(screen.getByText('abc123')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /back to timeline/i })).toBeInTheDocument();
  });

  it('shows an error state for an unknown memory', async () => {
    vi.mocked(getMemory).mockRejectedValueOnce(new Error('Memory not found'));
    renderDetail('does-not-exist');
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Memory not found');
    });
  });

  it('asks for confirmation and deletes through the API', async () => {
    const user = userEvent.setup();
    renderDetail('saved-1');
    await waitFor(() => screen.getByRole('button', { name: /delete memory/i }));
    await user.click(screen.getByRole('button', { name: /delete memory/i }));
    expect(screen.getByRole('button', { name: /yes, delete/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /yes, delete/i }));
    expect(await screen.findByText('Timeline screen')).toBeInTheDocument();
    expect(deleteMemory).toHaveBeenCalledWith('saved-1');
  });

  it('generates a summary on request and shows the summary with its model', async () => {
    const user = userEvent.setup();
    renderDetail('saved-1');
    await waitFor(() => screen.getByRole('button', { name: /delete memory/i }));

    await user.click(screen.getByRole('button', { name: /generate ai summary/i }));

    expect(summarizeMemory).toHaveBeenCalledTimes(1);
    expect(vi.mocked(summarizeMemory).mock.calls[0][0]).toBe('saved-1');
    expect(await screen.findByText(/First bullet of the summary/)).toBeInTheDocument();
    expect(screen.getByText('llama3.2:1b')).toBeInTheDocument();
    // Summary stays on screen with a regenerate option.
    expect(screen.getByRole('button', { name: /regenerate summary/i })).toBeInTheDocument();
  });

  it('shows a loading state and ignores duplicate clicks while generating', async () => {
    const user = userEvent.setup();
    let resolveSummary!: (value: MemorySummary) => void;
    vi.mocked(summarizeMemory).mockReturnValue(
      new Promise<MemorySummary>((resolve) => {
        resolveSummary = resolve;
      }),
    );
    renderDetail('saved-1');
    await waitFor(() => screen.getByRole('button', { name: /delete memory/i }));

    await user.click(screen.getByRole('button', { name: /generate ai summary/i }));

    const busyButton = await screen.findByRole('button', { name: /generating/i });
    expect(busyButton).toBeDisabled();
    expect(screen.getByRole('status')).toHaveTextContent(/local model/i);
    // Repeat clicks while running must not trigger a second request.
    await user.click(busyButton);
    expect(summarizeMemory).toHaveBeenCalledTimes(1);

    resolveSummary(summaryFixture);
    expect(await screen.findByText(/First bullet of the summary/)).toBeInTheDocument();
  });

  it('shows the backend error message when generation fails and allows retry', async () => {
    const user = userEvent.setup();
    vi.mocked(summarizeMemory).mockRejectedValueOnce(
      new Error('The local summarization model is unavailable on this server.'),
    );
    renderDetail('saved-1');
    await waitFor(() => screen.getByRole('button', { name: /delete memory/i }));

    await user.click(screen.getByRole('button', { name: /generate ai summary/i }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('The local summarization model is unavailable on this server.');
    // No stack traces or internal details leak into the UI.
    expect(alert.textContent ?? '').not.toMatch(/Error:|at .*\.js:|traceback/i);
    // The button is usable again for a retry.
    const retryButton = screen.getByRole('button', { name: /generate ai summary/i });
    expect(retryButton).not.toBeDisabled();
    await user.click(retryButton);
    expect(summarizeMemory).toHaveBeenCalledTimes(2);
  });

  it('discards a stale response after navigating to a different memory', async () => {
    const user = userEvent.setup();
    vi.mocked(getMemory).mockImplementation((id: string) =>
      Promise.resolve(id === 'saved-2' ? { memory: memoryTwo, source } : { memory, source }),
    );
    let resolveStale!: (value: MemorySummary) => void;
    vi.mocked(summarizeMemory).mockReturnValue(
      new Promise<MemorySummary>((resolve) => {
        resolveStale = resolve;
      }),
    );
    render(
      <MemoryRouter initialEntries={['/memory/saved-1']}>
        <NavigationHelper to="/memory/saved-2" label="open-second-memory" />
        <Routes>
          <Route path="/memory/:id" element={<MemoryDetail />} />
          <Route path="/timeline" element={<div>Timeline screen</div>} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByRole('button', { name: /delete memory/i }));

    await user.click(screen.getByRole('button', { name: /generate ai summary/i }));
    await screen.findByRole('button', { name: /generating/i });

    // Navigate while the first request is still in flight.
    await user.click(screen.getByRole('button', { name: 'open-second-memory' }));
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Second saved memory' })).toBeInTheDocument(),
    );

    // The stale response for the first memory must never appear on the second.
    resolveStale({ memory_id: 'saved-1', summary: 'STALE summary of first memory', model: 'llama3.2:1b' });
    await screen.findByRole('button', { name: /generate ai summary/i });
    expect(screen.queryByText(/STALE summary/)).not.toBeInTheDocument();

    // A fresh request targets the correct (second) memory and displays its summary.
    vi.mocked(summarizeMemory).mockResolvedValue({
      memory_id: 'saved-2',
      summary: 'Summary specific to the second memory.',
      model: 'llama3.2:1b',
    });
    await user.click(screen.getByRole('button', { name: /generate ai summary/i }));
    expect(await screen.findByText(/Summary specific to the second memory/)).toBeInTheDocument();
    const calls = vi.mocked(summarizeMemory).mock.calls;
    expect(calls[calls.length - 1][0]).toBe('saved-2');
  });
});
