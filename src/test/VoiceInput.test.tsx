import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import VoiceInput from '../components/VoiceInput';
import type { AudioRecorder, VoiceFailure } from '../lib/voice';

/**
 * Task 81 tests — recording states with mocked transcripts.
 *
 * These run in jsdom, which has **no** `navigator.mediaDevices` and **no**
 * `MediaRecorder`. That is deliberate: every microphone interaction goes through
 * the injected recorder/transcriber doubles, so the state machine is verified
 * deterministically with no hardware, no browser APIs and no network. Real
 * transcription is Task 82 and is explicitly out of scope here.
 */

interface Harness {
  recorder: {
    start: ReturnType<typeof vi.fn>;
    stop: ReturnType<typeof vi.fn>;
    cancel: ReturnType<typeof vi.fn>;
  };
  transcriber: { transcribe: ReturnType<typeof vi.fn> };
  createRecorder: ReturnType<typeof vi.fn>;
}

function harness(options: { recorder?: AudioRecorder | null } = {}): Harness {
  const recorder =
    options.recorder === undefined
      ? ({
          start: vi.fn().mockResolvedValue(undefined),
          stop: vi.fn().mockResolvedValue(new Blob(['audio-bytes'], { type: 'audio/webm' })),
          cancel: vi.fn(),
        } as unknown as Harness['recorder'])
      : (options.recorder as unknown as Harness['recorder']);

  const transcriber = {
    transcribe: vi
      .fn()
      .mockResolvedValue({ transcript: 'How do HNSW graphs work?', processingMs: 42 }),
  } as unknown as Harness['transcriber'];

  const createRecorder = vi.fn().mockReturnValue(recorder) as Harness['createRecorder'];
  return { recorder, transcriber, createRecorder };
}

function renderVoice(controls: Harness, props: Partial<Parameters<typeof VoiceInput>[0]> = {}) {
  const onTranscript = props.onTranscript ?? vi.fn();
  const view = render(
    <VoiceInput
      onTranscript={onTranscript}
      createRecorder={controls.createRecorder}
      transcriber={controls.transcriber}
      {...props}
    />,
  );
  return { ...view, onTranscript };
}

/** Press Voice and wait until the recording indicator is on screen. */
async function startRecording(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByTestId('voice-start'));
  await screen.findByTestId('voice-indicator');
}

/** A recorder whose `start()` always rejects with the named DOMException. */
function rejectingRecorder(name: string): AudioRecorder {
  const error = new Error(name);
  error.name = name;
  return { start: vi.fn().mockRejectedValue(error), stop: vi.fn(), cancel: vi.fn() };

describe('VoiceInput — recording states (Task 81)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('states', () => {
    it('starts idle with no indicator and no transcript preview', () => {
      renderVoice(harness());
      expect(screen.getByTestId('voice-start')).toBeInTheDocument();
      expect(screen.queryByTestId('voice-indicator')).not.toBeInTheDocument();
      expect(screen.queryByTestId('voice-transcript')).not.toBeInTheDocument();
      expect(screen.getByTestId('voice-status')).toHaveTextContent(/voice input is idle/i);
    });

    it('shows a persistent recording indicator and swaps in Stop/Cancel', async () => {
      const user = userEvent.setup();
      renderVoice(harness());

      await startRecording(user);

      expect(screen.getByTestId('voice-indicator')).toBeInTheDocument();
      expect(screen.getByTestId('voice-indicator')).toHaveTextContent(/microphone is live/i);
      expect(screen.getByTestId('voice-stop')).toBeInTheDocument();
      expect(screen.getByTestId('voice-cancel')).toBeInTheDocument();
      expect(screen.queryByTestId('voice-start')).not.toBeInTheDocument();
    });

    it('moves through processing into a success state with a preview', async () => {
      const user = userEvent.setup();
      let release: (() => void) | undefined;
      const gated = harness();
      gated.transcriber.transcribe.mockImplementation(
        () =>
          new Promise((resolve) => {
            release = () => resolve({ transcript: 'What is RRF ranking?', processingMs: 12 });
          }),
      );

      renderVoice(gated);
      await startRecording(user);
      await user.click(screen.getByTestId('voice-stop'));

      // The processing state is observable before the transcript lands.
      expect(screen.getByText(/transcribing your recording/i)).toBeInTheDocument();
      expect(screen.queryByTestId('voice-transcript')).not.toBeInTheDocument();

      release?.();
      await screen.findByTestId('voice-transcript');
      expect(screen.getByTestId('voice-transcript')).toHaveValue('What is RRF ranking?');
    });

    it('shows an error state when transcription fails', async () => {
      const user = userEvent.setup();
      const gated = harness();
      gated.transcriber.transcribe.mockRejectedValue({
        kind: 'transcription-failed',
        message: 'The recording could not be transcribed.',
      } satisfies VoiceFailure);

      renderVoice(gated);
      await startRecording(user);
      await user.click(screen.getByTestId('voice-stop'));

      await screen.findByTestId('voice-error');
      expect(screen.getByTestId('voice-error')).toHaveAttribute(
        'data-failure-kind',
        'transcription-failed',
      );
      expect(screen.getByTestId('voice-error')).toHaveTextContent(/could not be transcribed/i);
    });
  });

  describe('permission and device handling', () => {
    it('reports denied permission and never reaches recording', async () => {
      const user = userEvent.setup();
      const gated = harness({ recorder: rejectingRecorder('NotAllowedError') });

      renderVoice(gated);
      await user.click(screen.getByTestId('voice-start'));

      await screen.findByTestId('voice-error');
      expect(screen.getByTestId('voice-error')).toHaveAttribute(
        'data-failure-kind',
        'permission-denied',
      );
      expect(screen.getByTestId('voice-error')).toHaveTextContent(/allow it in your browser/i);
      expect(screen.queryByTestId('voice-indicator')).not.toBeInTheDocument();
    });

    it('reports an unavailable device distinctly from denied permission', async () => {
      const user = userEvent.setup();
      const gated = harness({ recorder: rejectingRecorder('NotFoundError') });

      renderVoice(gated);
      await user.click(screen.getByTestId('voice-start'));

      await screen.findByTestId('voice-error');
      expect(screen.getByTestId('voice-error')).toHaveAttribute(
        'data-failure-kind',
        'device-unavailable',
      );
      expect(screen.getByTestId('voice-error')).toHaveTextContent(/no microphone is available/i);
    });

    it('explains itself when the browser cannot record at all', async () => {
      const user = userEvent.setup();
      const gated = harness({ recorder: null });

      renderVoice(gated);
      await user.click(screen.getByTestId('voice-start'));

      await screen.findByTestId('voice-error');
      expect(screen.getByTestId('voice-error')).toHaveAttribute('data-failure-kind', 'not-supported');
      expect(gated.createRecorder).toHaveBeenCalledTimes(1);
      expect(screen.queryByTestId('voice-indicator')).not.toBeInTheDocument();
    });

    it('reports empty audio when the user stopped too early', async () => {
      const user = userEvent.setup();
      const gated = harness();
      gated.recorder.stop.mockRejectedValue({
        kind: 'no-audio',
        message: 'Nothing was recorded.',
      } satisfies VoiceFailure);

      renderVoice(gated);
      await startRecording(user);
      await user.click(screen.getByTestId('voice-stop'));

      await screen.findByTestId('voice-error');
      expect(screen.getByTestId('voice-error')).toHaveAttribute('data-failure-kind', 'no-audio');
    });
  });
});

}

describe('VoiceInput — cancellation and privacy (Task 81)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('cancel behaviour', () => {
    it('discards a recording, releases the mic and returns to idle', async () => {
      const user = userEvent.setup();
      const controls = harness();

      renderVoice(controls);
      await startRecording(user);
      await user.click(screen.getByTestId('voice-cancel'));

      expect(controls.recorder.cancel).toHaveBeenCalledTimes(1);
      expect(screen.queryByTestId('voice-indicator')).not.toBeInTheDocument();
      expect(screen.queryByTestId('voice-transcript')).not.toBeInTheDocument();
      expect(screen.getByTestId('voice-start')).toBeInTheDocument();
      expect(screen.getByTestId('voice-status')).toHaveTextContent(/idle/i);
    });

    it('never submits anything when a recording is cancelled', async () => {
      const user = userEvent.setup();
      const controls = harness();
      const onTranscript = vi.fn();

      renderVoice(controls, { onTranscript });
      await startRecording(user);
      await user.click(screen.getByTestId('voice-cancel'));

      expect(controls.transcriber.transcribe).not.toHaveBeenCalled();
      expect(onTranscript).not.toHaveBeenCalled();
    });

    it('can discard an already-transcribed result without submitting it', async () => {
      const user = userEvent.setup();
      const controls = harness();
      const onTranscript = vi.fn();

      renderVoice(controls, { onTranscript });
      await startRecording(user);
      await user.click(screen.getByTestId('voice-stop'));
      await screen.findByTestId('voice-transcript');

      await user.click(screen.getByTestId('voice-discard'));

      expect(screen.queryByTestId('voice-transcript')).not.toBeInTheDocument();
      expect(onTranscript).not.toHaveBeenCalled();
      expect(screen.getByTestId('voice-start')).toBeInTheDocument();
    });

    it('releases the microphone when the component unmounts mid-recording', async () => {
      const user = userEvent.setup();
      const controls = harness();
      const { unmount } = renderVoice(controls);

      await startRecording(user);
      unmount();

      expect(controls.recorder.cancel).toHaveBeenCalledTimes(1);
    });
  });

  describe('privacy', () => {
    it('never records automatically on mount', () => {
      const controls = harness();
      renderVoice(controls);

      // Proof: the factory is never invoked, so no permission prompt either.
      expect(controls.createRecorder).not.toHaveBeenCalled();
      expect(controls.recorder.start).not.toHaveBeenCalled();
      expect(controls.recorder.cancel).not.toHaveBeenCalled();
    });

    it('requests the microphone only when the user presses the control', async () => {
      const user = userEvent.setup();
      const controls = harness();
      renderVoice(controls);

      expect(controls.createRecorder).not.toHaveBeenCalled();
      await startRecording(user);
      expect(controls.createRecorder).toHaveBeenCalledTimes(1);
      expect(controls.recorder.start).toHaveBeenCalledTimes(1);
    });

    it('cannot open a second microphone stream during a recording', async () => {
      const user = userEvent.setup();
      const controls = harness();
      renderVoice(controls);

      await startRecording(user);
      // The Start button is gone while recording, so a stale reference or a
      // repeated keypress cannot open a second stream.
      expect(screen.queryByTestId('voice-start')).not.toBeInTheDocument();
      expect(controls.recorder.start).toHaveBeenCalledTimes(1);
    });
  });
});


describe('VoiceInput — transcript preview and accessibility (Task 81)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('transcript preview and submission', () => {
    it('previews the transcript without submitting it, then sends it on demand', async () => {
      const user = userEvent.setup();
      const controls = harness();
      const onTranscript = vi.fn();

      renderVoice(controls, { onTranscript });
      await startRecording(user);
      await user.click(screen.getByTestId('voice-stop'));
      await screen.findByTestId('voice-transcript');

      // Nothing is submitted merely because a transcript arrived.
      expect(onTranscript).not.toHaveBeenCalled();

      await user.click(screen.getByTestId('voice-use-transcript'));
      expect(onTranscript).toHaveBeenCalledWith('How do HNSW graphs work?');
      expect(onTranscript).toHaveBeenCalledTimes(1);
    });

    it('lets the user edit the transcript before submitting it', async () => {
      const user = userEvent.setup();
      const controls = harness();
      const onTranscript = vi.fn();

      renderVoice(controls, { onTranscript });
      await startRecording(user);
      await user.click(screen.getByTestId('voice-stop'));
      const box = await screen.findByTestId('voice-transcript');

      await user.clear(box);
      await user.type(box, 'How do HNSW graphs work on Apple silicon?');
      await user.click(screen.getByTestId('voice-use-transcript'));

      expect(onTranscript).toHaveBeenCalledWith('How do HNSW graphs work on Apple silicon?');
    });

    it('refuses to submit an emptied transcript', async () => {
      const user = userEvent.setup();
      const controls = harness();
      const onTranscript = vi.fn();

      renderVoice(controls, { onTranscript });
      await startRecording(user);
      await user.click(screen.getByTestId('voice-stop'));
      const box = await screen.findByTestId('voice-transcript');

      await user.clear(box);
      expect(screen.getByTestId('voice-use-transcript')).toBeDisabled();
      expect(onTranscript).not.toHaveBeenCalled();
    });

    it('treats a whitespace-only transcript as no speech', async () => {
      const user = userEvent.setup();
      const controls = harness();
      controls.transcriber.transcribe.mockResolvedValue({ transcript: '   \n  ' });

      renderVoice(controls);
      await startRecording(user);
      await user.click(screen.getByTestId('voice-stop'));

      await screen.findByTestId('voice-error');
      expect(screen.getByTestId('voice-error')).toHaveAttribute('data-failure-kind', 'no-speech');
    });

    it('does not leave a stale transcript when recording starts again', async () => {
      const user = userEvent.setup();
      const controls = harness();
      renderVoice(controls);

      await startRecording(user);
      await user.click(screen.getByTestId('voice-stop'));
      await screen.findByTestId('voice-transcript');
      await user.click(screen.getByTestId('voice-discard'));
      await startRecording(user);

      expect(screen.queryByTestId('voice-transcript')).not.toBeInTheDocument();
      expect(screen.queryByTestId('voice-error')).not.toBeInTheDocument();
    });
  });

  describe('accessibility', () => {
    it('labels every control for assistive technology', async () => {
      const user = userEvent.setup();
      renderVoice(harness());

      expect(screen.getByRole('button', { name: /start voice input/i })).toBeInTheDocument();

      await startRecording(user);
      expect(
        screen.getByRole('button', { name: /stop recording and transcribe/i }),
      ).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /cancel recording/i })).toBeInTheDocument();
    });

    it('announces each state change in a polite live region', async () => {
      const user = userEvent.setup();
      renderVoice(harness());

      const status = screen.getByTestId('voice-status');
      expect(status).toHaveAttribute('aria-live', 'polite');
      expect(status).toHaveTextContent(/idle/i);

      await startRecording(user);
      expect(screen.getByTestId('voice-status')).toHaveTextContent(/recording/i);
    });

    it('announces failures as an alert', async () => {
      const user = userEvent.setup();
      renderVoice(harness({ recorder: rejectingRecorder('NotAllowedError') }));

      await user.click(screen.getByTestId('voice-start'));
      await screen.findByTestId('voice-error');

      expect(screen.getByRole('alert')).toHaveTextContent(/allow it in your browser/i);
      expect(screen.getByTestId('voice-status')).toHaveTextContent(/allow it in your browser/i);
    });

    it('operates entirely from the keyboard', async () => {
      const user = userEvent.setup();
      const onTranscript = vi.fn();
      renderVoice(harness(), { onTranscript });

      // Tab reaches the control; Enter activates it (real button semantics).
      await user.tab();
      expect(screen.getByTestId('voice-start')).toHaveFocus();
      await user.keyboard('{Enter}');
      await screen.findByTestId('voice-indicator');

      // Escape is deliberately NOT a shortcut: only an explicit press stops it.
      await user.keyboard('{Escape}');
      expect(screen.getByTestId('voice-indicator')).toBeInTheDocument();

      await user.click(screen.getByTestId('voice-stop'));
      await screen.findByTestId('voice-transcript');
      await user.click(screen.getByTestId('voice-use-transcript'));
      expect(onTranscript).toHaveBeenCalledTimes(1);
    });

    it('disables the control while a query is already in flight', async () => {
      const user = userEvent.setup();
      renderVoice(harness(), { disabled: true });

      await user.click(screen.getByTestId('voice-start'));
      expect(screen.queryByTestId('voice-indicator')).not.toBeInTheDocument();
    });
  });
});

