import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import MemoryDetail from '../pages/MemoryDetail';
import { MemoriesProvider } from '../state/MemoriesContext';

function renderDetail(id: string) {
  return render(
    <MemoryRouter initialEntries={[`/memory/${id}`]}>
      <MemoriesProvider>
        <Routes>
          <Route path="/memory/:id" element={<MemoryDetail />} />
          <Route path="/timeline" element={<div>Timeline screen</div>} />
        </Routes>
      </MemoriesProvider>
    </MemoryRouter>,
  );
}

describe('Memory Detail', () => {
  it('renders the memory content and a back link', async () => {
    renderDetail('mem-001');
    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /Attention Mechanisms in Lightweight Vision Transformers/i }),
      ).toBeInTheDocument();
    });
    expect(screen.getByRole('link', { name: /back to timeline/i })).toBeInTheDocument();
  });

  it('shows an error state for an unknown memory', async () => {
    renderDetail('does-not-exist');
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
  });

  it('asks for confirmation before deleting', async () => {
    const user = userEvent.setup();
    renderDetail('mem-001');
    await waitFor(() => screen.getByRole('button', { name: /delete memory/i }));
    await user.click(screen.getByRole('button', { name: /delete memory/i }));
    expect(screen.getByRole('button', { name: /yes, delete/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
  });
});
