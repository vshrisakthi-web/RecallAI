import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import MemoryTimeline from '../pages/MemoryTimeline';
import { listMemories } from '../lib/memoriesApi';
import type { Memory } from '../data/types';

vi.mock('../lib/memoriesApi', () => ({
  listMemories: vi.fn(),
}));

const memory: Memory = {
  id: 'saved-1',
  title: 'SQLite search notes',
  excerpt: 'FTS finds words in saved content.',
  content: 'FTS finds words in saved content.',
  sourceType: 'browser',
  sourceName: 'docs.example',
  sourceUrl: 'https://docs.example/sqlite',
  capturedAt: '2026-10-10T08:00:00Z',
  capturedLabel: 'Oct 10, 2026, 8:00 AM',
  tags: [],
  localOnly: true,
  sourceId: 'source-1',
};

const page = {
  items: [memory],
  page: 1,
  page_size: 12,
  total: 1,
  total_pages: 1,
};

function renderTimeline() {
  return render(
    <MemoryRouter>
      <MemoryTimeline />
    </MemoryRouter>,
  );
}

describe('Memory Timeline', () => {
  beforeEach(() => {
    vi.mocked(listMemories).mockReset();
    vi.mocked(listMemories).mockResolvedValue(page);
  });

  it('shows loading before rendering actual API records', async () => {
    let resolveRequest!: (value: typeof page) => void;
    vi.mocked(listMemories).mockReturnValueOnce(
      new Promise((resolve) => { resolveRequest = resolve; }),
    );
    renderTimeline();
    expect(screen.getByRole('status')).toHaveTextContent('Loading saved memories');
    resolveRequest(page);
    expect(await screen.findByRole('heading', { name: 'SQLite search notes' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /SQLite search notes/ })).toHaveAttribute(
      'href',
      '/memory/saved-1',
    );
  });

  it('shows a real empty state', async () => {
    vi.mocked(listMemories).mockResolvedValueOnce({ ...page, items: [], total: 0, total_pages: 0 });
    renderTimeline();
    expect(await screen.findByText('No memories yet')).toBeInTheDocument();
  });

  it('shows a no-results state for a filtered query', async () => {
    renderTimeline();
    await screen.findByRole('heading', { name: 'SQLite search notes' });
    vi.mocked(listMemories).mockResolvedValue({ ...page, items: [], total: 0, total_pages: 0 });
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search memories' }), {
      target: { value: 'nothing matches' },
    });
    expect(await screen.findByText('No matches')).toBeInTheDocument();
  });

  it('sends search, date, domain, and source filters to the API', async () => {
    const user = userEvent.setup();
    renderTimeline();
    await screen.findByRole('heading', { name: 'SQLite search notes' });

    await user.type(screen.getByRole('searchbox', { name: 'Search memories' }), 'vector search');
    await user.selectOptions(screen.getByLabelText('Filter by source type'), 'browser');
    await user.type(screen.getByLabelText('Filter by domain'), 'docs.example');
    await user.type(screen.getByLabelText('From date'), '2026-10-01');
    await user.type(screen.getByLabelText('To date'), '2026-10-11');

    await waitFor(() => {
      const latest = vi.mocked(listMemories).mock.calls.at(-1)?.[0];
      expect(latest).toMatchObject({
        q: 'vector search',
        source_type: 'browser',
        domain: 'docs.example',
        from_date: '2026-10-01',
        to_date: '2026-10-11',
        page: 1,
      });
    });
  });

  it('requests the next page from the API', async () => {
    const user = userEvent.setup();
    vi.mocked(listMemories).mockResolvedValueOnce({ ...page, total: 13, total_pages: 2 });
    vi.mocked(listMemories).mockResolvedValueOnce({
      ...page,
      page: 2,
      total: 13,
      total_pages: 2,
      items: [{ ...memory, id: 'saved-2', title: 'Second page record' }],
    });
    renderTimeline();
    await screen.findByRole('heading', { name: 'SQLite search notes' });
    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(await screen.findByRole('heading', { name: 'Second page record' })).toBeInTheDocument();
    await waitFor(() => {
      expect(vi.mocked(listMemories).mock.calls.at(-1)?.[0].page).toBe(2);
    });
  });

  it('shows a retryable backend error without mock fallback', async () => {
    const user = userEvent.setup();
    vi.mocked(listMemories).mockRejectedValueOnce(new Error('Backend unavailable'));
    renderTimeline();
    expect(await screen.findByRole('alert')).toHaveTextContent('Backend unavailable');
    vi.mocked(listMemories).mockResolvedValueOnce(page);
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('heading', { name: 'SQLite search notes' })).toBeInTheDocument();
  });
});
