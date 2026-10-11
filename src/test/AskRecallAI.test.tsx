import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import AskRecallAI from '../pages/AskRecallAI';
import { MemoriesProvider } from '../state/MemoriesContext';

function renderAsk() {
  return render(
    <MemoryRouter>
      <MemoriesProvider>
        <AskRecallAI />
      </MemoriesProvider>
    </MemoryRouter>,
  );
}

describe('Ask RecallAI', () => {
  it('labels every answer as a mock answer', () => {
    renderAsk();
    // Seeded conversation already shows a mock badge.
    const badges = screen.getAllByTestId('mock-answer-badge');
    expect(badges.length).toBeGreaterThan(0);
    expect(badges[0]).toHaveTextContent(/mock answer/i);
  });

  it('appends a new mock answer when a question is asked', async () => {
    const user = userEvent.setup();
    renderAsk();
    const before = screen.getAllByTestId('mock-answer-badge').length;
    const input = screen.getByLabelText(/ask a question/i);
    await user.type(input, 'design tokens');
    await user.click(screen.getByRole('button', { name: /^ask$/i }));
    await waitFor(() => {
      expect(screen.getAllByTestId('mock-answer-badge').length).toBe(before + 1);
    });
  });

  it('shows an error state when simulated', async () => {
    const user = userEvent.setup();
    renderAsk();
    await user.click(screen.getByRole('button', { name: /simulate error/i }));
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
  });
});
