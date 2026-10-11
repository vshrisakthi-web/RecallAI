import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Overview from '../pages/Overview';
import { MemoriesProvider } from '../state/MemoriesContext';

function renderOverview() {
  return render(
    <MemoryRouter>
      <MemoriesProvider>
        <Overview />
      </MemoriesProvider>
    </MemoryRouter>,
  );
}

describe('Overview dashboard', () => {
  it('renders the heading and activity summary', () => {
    renderOverview();
    expect(screen.getByRole('heading', { name: /overview/i })).toBeInTheDocument();
    expect(screen.getByText(/Universal Context Search/i)).toBeInTheDocument();
    expect(screen.getByText(/Total Memories/i)).toBeInTheDocument();
  });

  it('shows recent memory cards from mock data', () => {
    renderOverview();
    expect(
      screen.getByText(/Attention Mechanisms in Lightweight Vision Transformers/i),
    ).toBeInTheDocument();
  });

  it('filters memories by search query', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const user = userEvent.setup();
    renderOverview();
    const search = screen.getByLabelText(/search memories/i);
    await user.type(search, 'sqlite');
    expect(screen.getByText(/sqlite-vss/i)).toBeInTheDocument();
    expect(
      screen.queryByText(/Attention Mechanisms in Lightweight Vision Transformers/i),
    ).not.toBeInTheDocument();
  });
});
