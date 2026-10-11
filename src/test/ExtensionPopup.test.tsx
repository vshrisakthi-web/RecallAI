import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import ExtensionPopup from '../pages/ExtensionPopup';

function renderPopup() {
  return render(
    <MemoryRouter>
      <ExtensionPopup />
    </MemoryRouter>,
  );
}

describe('Chrome extension popup — capture states', () => {
  it('starts in the Active state with Pause/Stop controls', () => {
    renderPopup();
    expect(screen.getByTestId('popup-state-active')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /pause/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /stop/i })).toBeInTheDocument();
  });

  it('transitions Active → Paused and shows Resume', async () => {
    const user = userEvent.setup();
    renderPopup();
    await user.click(screen.getByRole('button', { name: /pause/i }));
    expect(screen.getByTestId('popup-state-paused')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /resume/i })).toBeInTheDocument();
  });

  it('transitions to Stopped and shows Start Capture', async () => {
    const user = userEvent.setup();
    renderPopup();
    await user.click(screen.getByRole('button', { name: /stop/i }));
    expect(screen.getByTestId('popup-state-stopped')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /start capture/i })).toBeInTheDocument();
  });

  it('can restart from Stopped', async () => {
    const user = userEvent.setup();
    renderPopup();
    await user.click(screen.getByRole('button', { name: /stop/i }));
    await user.click(screen.getByRole('button', { name: /start capture/i }));
    expect(screen.getByTestId('popup-state-active')).toBeInTheDocument();
  });
});
