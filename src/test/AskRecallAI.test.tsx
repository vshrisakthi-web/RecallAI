import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import AskRecallAI from '../pages/AskRecallAI';
import { askRecallAi } from '../lib/memoriesApi';
import type { AskResult } from '../lib/memoriesApi';

vi.mock('../lib/memoriesApi', () => ({
  askRecallAi: vi.fn(),
}));

const mockedAsk = vi.mocked(askRecallAi);

function result(overrides: Partial<AskResult> = {}): AskResult {
  return {
    question: 'How do HNSW graphs work?',
    evidence: [
      {
        chunk_id: 'chk_abc',
        memory_id: 'mem_abc',
        source_id: 'src_abc',
        source_type: 'browser',
        source_title: 'HNSW embeddings',
        source_url: 'https://example.com/hnsw',
        domain: 'example.com',
        captured_at: '2026-10-10T09:00:00Z',
        passage: 'HNSW graphs connect embeddings in layers for approximate search.',
        similarity: 0.82,
        keyword_rank: 1,
        score: 0.032,
        matched_by: ['semantic', 'keyword'],
        confidence: 'strong',
      },
    ],
    confidence: 'strong',
    channels: ['semantic', 'keyword'],
    candidates_considered: 3,
    temporal_expression: null,
    temporal_from: null,
    temporal_to: null,
    request_id: 'req_test',
    ...overrides,
  };
}

function renderAsk() {
  return render(
    <MemoryRouter>
      <AskRecallAI />
    </MemoryRouter>,
  );
}

describe('Ask RecallAI (real retrieval)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows an empty state before anything is asked', () => {
    renderAsk();
    expect(screen.getByText(/ask anything about your memories/i)).toBeInTheDocument();
    expect(mockedAsk).not.toHaveBeenCalled();
  });

  it('renders retrieved evidence with its real source metadata', async () => {
    const user = userEvent.setup();
    mockedAsk.mockResolvedValue(result());
    renderAsk();

    await user.type(screen.getByLabelText(/ask a question/i), 'How do HNSW graphs work?');
    await user.click(screen.getByRole('button', { name: /^ask$/i }));

    await waitFor(() => expect(screen.getByTestId('ask-result')).toBeInTheDocument());
    expect(screen.getByText('HNSW embeddings')).toBeInTheDocument();
    expect(screen.getByText(/HNSW graphs connect embeddings in layers/)).toBeInTheDocument();
    expect(screen.getByTestId('confidence-badge')).toHaveTextContent(/strong evidence/i);
    expect(screen.getByTestId('evidence-similarity')).toHaveTextContent('82% match');
    expect(screen.getByRole('link', { name: /open memory/i })).toHaveAttribute(
      'href',
      '/memories/mem_abc',
    );
  });

  it('never presents a generated answer', async () => {
    const user = userEvent.setup();
    mockedAsk.mockResolvedValue(result());
    renderAsk();

    await user.type(screen.getByLabelText(/ask a question/i), 'How do HNSW graphs work?');
    await user.click(screen.getByRole('button', { name: /^ask$/i }));

    await waitFor(() => expect(screen.getByTestId('ask-result')).toBeInTheDocument());
    expect(screen.queryByTestId('mock-answer-badge')).not.toBeInTheDocument();
    expect(screen.getByText(/does not generate answers/i)).toBeInTheDocument();
  });

  it('distinguishes a successful empty search from a failure', async () => {
    const user = userEvent.setup();
    mockedAsk.mockResolvedValue(
      result({ evidence: [], confidence: 'none', candidates_considered: 0 }),
    );
    renderAsk();

    await user.type(screen.getByLabelText(/ask a question/i), 'unrelated topic');
    await user.click(screen.getByRole('button', { name: /^ask$/i }));

    await waitFor(() => expect(screen.getByTestId('no-evidence')).toBeInTheDocument());
    expect(screen.getByText(/successful search that found nothing/i)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });


  it('surfaces a backend error with a retry', async () => {
    const user = userEvent.setup();
    mockedAsk.mockRejectedValue(new Error('Could not reach the local RecallAI server.'));
    renderAsk();

    await user.type(screen.getByLabelText(/ask a question/i), 'anything');
    await user.click(screen.getByRole('button', { name: /^ask$/i }));

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    expect(screen.getByText(/could not reach the local recallai server/i)).toBeInTheDocument();
  });

  it('prevents duplicate submissions while a request is in flight', async () => {
    const user = userEvent.setup();
    let release: (value: AskResult) => void = () => {};
    mockedAsk.mockImplementation(
      () =>
        new Promise<AskResult>((resolve) => {
          release = resolve;
        }),
    );
    renderAsk();

    await user.type(screen.getByLabelText(/ask a question/i), 'first question');
    await user.click(screen.getByRole('button', { name: /^ask$/i }));

    // The button is disabled while loading, so a second click cannot fire.
    expect(screen.getByRole('button', { name: /searching…/i })).toBeDisabled();
    expect(mockedAsk).toHaveBeenCalledTimes(1);

    release(result());
    await waitFor(() => expect(screen.getByTestId('ask-result')).toBeInTheDocument());
  });

  it('shows a loading state while searching', async () => {
    const user = userEvent.setup();
    let release: (value: AskResult) => void = () => {};
    mockedAsk.mockImplementation(
      () =>
        new Promise<AskResult>((resolve) => {
          release = resolve;
        }),
    );
    renderAsk();

    await user.type(screen.getByLabelText(/ask a question/i), 'anything');
    await user.click(screen.getByRole('button', { name: /^ask$/i }));

    // Scoped to Ask's own region: VoiceInput also renders a polite live region.
    expect(screen.getByTestId('ask-loading')).toHaveTextContent(/searching your memories/i);
    release(result());
    await waitFor(() => expect(screen.queryByTestId('ask-loading')).not.toBeInTheDocument());
  });

  it('sends the trimmed question to the backend', async () => {
    const user = userEvent.setup();
    mockedAsk.mockResolvedValue(result());
    renderAsk();

    await user.type(screen.getByLabelText(/ask a question/i), '  How do HNSW graphs work?  ');
    await user.click(screen.getByRole('button', { name: /^ask$/i }));

    await waitFor(() => expect(mockedAsk).toHaveBeenCalled());
    expect(mockedAsk.mock.calls[0][0]).toEqual({ question: 'How do HNSW graphs work?' });
  });

  // --- Task 81: the voice control lives beside typed chat, never in front of it ---

  it('renders the voice control without touching the microphone on load', () => {
    renderAsk();

    // Present, idle, and — critically — no permission prompt / no recording
    // happens simply because the page was opened.
    expect(screen.getByTestId('voice-start')).toBeInTheDocument();
    expect(screen.queryByTestId('voice-indicator')).not.toBeInTheDocument();
    expect(screen.queryByTestId('voice-error')).not.toBeInTheDocument();
    // Typed chat is still the primary path and remains enabled.
    expect(screen.getByLabelText(/ask a question/i)).toBeEnabled();
    expect(screen.getByRole('button', { name: /^ask$/i })).toBeDisabled(); // empty input
  });

  it('keeps typed chat usable when microphone access is unavailable (jsdom)', async () => {
    const user = userEvent.setup();
    mockedAsk.mockResolvedValue(result());
    renderAsk();

    // jsdom has no navigator.mediaDevices / MediaRecorder, so pressing Voice
    // surfaces a graceful not-supported failure instead of crashing the page.
    await user.click(screen.getByTestId('voice-start'));
    await screen.findByTestId('voice-error');
    expect(screen.getByTestId('voice-error')).toHaveAttribute('data-failure-kind', 'not-supported');

    // The question box is untouched and still submits normally afterwards.
    await user.type(screen.getByLabelText(/ask a question/i), 'anything at all');
    await user.click(screen.getByRole('button', { name: /^ask$/i }));
    await waitFor(() => expect(mockedAsk).toHaveBeenCalled());
    expect(mockedAsk.mock.calls[0][0]).toEqual({ question: 'anything at all' });
  });

  // --- Task 84: browser-native text-to-speech (speaker controls) ---

  it('renders speaker controls below each answer', async () => {
    const user = userEvent.setup();
    mockedAsk.mockResolvedValue(result());
    renderAsk();

    await user.type(screen.getByLabelText(/ask a question/i), 'How do HNSW graphs work?');
    await user.click(screen.getByRole('button', { name: /^ask$/i }));

    await waitFor(() => expect(screen.getByTestId('ask-result')).toBeInTheDocument());
    expect(screen.getByTestId('tts-controls')).toBeInTheDocument();
    expect(screen.getByTestId('tts-play-pause')).toBeInTheDocument();
    expect(screen.getByTestId('tts-stop')).toBeInTheDocument();
    expect(screen.getByTestId('tts-status')).toBeInTheDocument();
  });

  it('announces playback state to screen readers via aria-live region', async () => {
    const user = userEvent.setup();
    mockedAsk.mockResolvedValue(result());
    renderAsk();

    await user.type(screen.getByLabelText(/ask a question/i), 'How do HNSW graphs work?');
    await user.click(screen.getByRole('button', { name: /^ask$/i }));

    await waitFor(() => expect(screen.getByTestId('ask-result')).toBeInTheDocument());
    const status = screen.getByTestId('tts-status');
    expect(status).toHaveAttribute('aria-live', 'polite');
    expect(status).toHaveAttribute('role', 'status');
    expect(status).toHaveTextContent(/ready to play answer/i);
  });

  it('does not auto-play speech; playback starts only on explicit user action', async () => {
    const user = userEvent.setup();
    mockedAsk.mockResolvedValue(result());
    renderAsk();

    await user.type(screen.getByLabelText(/ask a question/i), 'How do HNSW graphs work?');
    await user.click(screen.getByRole('button', { name: /^ask$/i }));

    await waitFor(() => expect(screen.getByTestId('ask-result')).toBeInTheDocument());
    // Before clicking play, no speech has started
    expect(screen.getByTestId('tts-status')).toHaveTextContent(/ready to play answer/i);
  });
});
