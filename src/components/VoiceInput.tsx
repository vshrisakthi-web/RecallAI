import { useCallback, useEffect, useRef, useState } from 'react';
import {
  createMediaRecorder,
  mapRecorderError,
  notConnectedTranscriber,
  type AudioRecorder,
  type RecorderFactory,
  type Transcriber,
  type VoiceFailure,
  type VoicePhase,
} from '../lib/voice';

/**
 * Microphone control and recording states (Module 9, Task 81).
 *
 * Sits next to the existing chat input and hands a *transcript* back to the
 * parent. It deliberately does not query anything itself: the parent puts the
 * transcript into the normal composer, so voice input flows through exactly the
 * same path as typing (wired up in Task 83).
 *
 * Design rules this component exists to enforce:
 *   * Recording begins only on an explicit press — never on mount.
 *   * A persistent indicator is visible the whole time the microphone is live.
 *   * Stop produces a transcript the user can read and edit before submitting.
 *   * Cancel discards everything and releases the microphone.
 *   * Every state is announced to assistive technology via an `aria-live` region,
 *     and every control is a real focusable button with a text label.
 *
 * The recorder and transcriber are injected, so tests drive deterministic
 * doubles in jsdom instead of touching a real microphone.
 */
export interface VoiceInputProps {
  /** Called with the transcript when the user accepts it. */
  onTranscript: (transcript: string) => void;
  /** Disables the control (e.g. while a query is in flight). */
  disabled?: boolean;
  /** Test seam; defaults to the browser `MediaRecorder` implementation. */
  createRecorder?: RecorderFactory;
  /** Test seam; defaults to the "not connected" transcriber until Task 82. */
  transcriber?: Transcriber;
}

/** The single user-facing status sentence for each phase. */
const PHASE_MESSAGE: Record<VoicePhase, string> = {
  idle: 'Voice input is idle.',
  'requesting-permission': 'Waiting for microphone permission…',
  recording: 'Recording… speak now.',
  processing: 'Transcribing your recording…',
  success: 'Transcript ready. Review it below before asking.',
  error: 'Voice input failed.',
};

export default function VoiceInput({
  onTranscript,
  disabled = false,
  createRecorder = createMediaRecorder,
  transcriber = notConnectedTranscriber,
}: VoiceInputProps) {
  const [phase, setPhase] = useState<VoicePhase>('idle');
  const [failure, setFailure] = useState<VoiceFailure | null>(null);
  const [transcript, setTranscript] = useState('');

  // The live recorder is kept in a ref, not state: it is a resource handle, not
  // render data, and cleanup must be able to reach it without a re-render.
  const recorderRef = useRef<AudioRecorder | null>(null);

  // Releases the microphone on unmount, so navigating away can never leave the
  // recording indicator on or the microphone hot.
  useEffect(
    () => () => {
      recorderRef.current?.cancel();
      recorderRef.current = null;
    },
    [],
  );

  const fail = useCallback((error: unknown) => {
    // A structured VoiceFailure passes through untouched; anything else (a raw
    // DOMException from getUserMedia, or an unexpected throw) is mapped onto a
    // safe, specific failure here so no browser internals reach the UI.
    const mapped: VoiceFailure =
      typeof error === 'object' &&
      error !== null &&
      'kind' in error &&
      'message' in error &&
      typeof (error as VoiceFailure).message === 'string'
        ? (error as VoiceFailure)
        : mapRecorderError(error);
    setFailure(mapped);
    setPhase('error');
  }, []);

  const reset = useCallback(() => {
    recorderRef.current?.cancel();
    recorderRef.current = null;
    setPhase('idle');
    setFailure(null);
    setTranscript('');
  }, []);

  const handleStart = useCallback(async () => {
    // Idempotence guard: a double press (or double Enter) must not open the
    // microphone twice.
    if (recorderRef.current || phase === 'recording' || phase === 'requesting-permission') return;

    const recorder = createRecorder();
    if (!recorder) {
      // jsdom, old browsers, or an enterprise policy that strips MediaRecorder.
      fail({
        kind: 'not-supported',
        message: 'This browser cannot record audio, so voice input is unavailable.',
      });
      return;
    }

    recorderRef.current = recorder;
    setFailure(null);
    setTranscript('');
    setPhase('requesting-permission');

    try {
      // Permission is requested here — only because the user pressed the button.
      await recorder.start();
      setPhase('recording');
    } catch (error) {
      recorderRef.current = null;
      fail(error);
    }
  }, [createRecorder, fail, phase]);

  const handleStop = useCallback(async () => {
    const recorder = recorderRef.current;
    if (!recorder || phase !== 'recording') return;

    setPhase('processing');
    let audio: Blob;
    try {
      audio = await recorder.stop();
    } catch (error) {
      recorderRef.current = null;
      fail(error);
      return;
    }
    recorderRef.current = null;

    try {
      const result = await transcriber.transcribe(audio);
      const text = result.transcript.trim();
      if (!text) {
        fail({ kind: 'no-speech', message: 'No speech was detected in that recording.' });
        return;
      }
      // The transcript is only *shown* here; the parent submits it, so the user
      // always gets to read and edit it first (Task 83).
      setTranscript(text);
      setPhase('success');
    } catch (error) {
      fail(error);
    }
  }, [fail, phase, transcriber]);

  const handleCancel = useCallback(() => {
    // Always legal: abort mid-permission-prompt, mid-recording, or after a
    // transcript. Nothing is kept and the microphone is released.
    reset();
  }, [reset]);

  const handleUseTranscript = useCallback(() => {
    const text = transcript.trim();
    if (!text) return;
    onTranscript(text);
    setTranscript('');
    setPhase('idle');
  }, [onTranscript, transcript]);

  const recording = phase === 'recording';
  const busy = phase === 'requesting-permission' || phase === 'processing';


  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {/* Start — hidden while recording; Stop/Cancel take its place. */}
        {!recording && (
          <button
            type="button"
            onClick={handleStart}
            disabled={disabled || busy}
            aria-label="Start voice input"
            data-testid="voice-start"
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-ink hover:border-brand-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <span aria-hidden="true">🎙</span>
            Voice
          </button>
        )}

        {/* Stop and Cancel exist only while the microphone is live. */}
        {recording && (
          <>
            <button
              type="button"
              onClick={handleStop}
              aria-label="Stop recording and transcribe"
              data-testid="voice-stop"
              className="inline-flex items-center gap-1.5 rounded-xl bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600"
            >
              <span aria-hidden="true">⏹</span>
              Stop
            </button>
            <button
              type="button"
              onClick={handleCancel}
              aria-label="Cancel recording"
              data-testid="voice-cancel"
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-ink hover:border-red-200 hover:text-red-700"
            >
              <span aria-hidden="true">✕</span>
              Cancel
            </button>
          </>
        )}

        {phase === 'success' && (
          <button
            type="button"
            onClick={handleCancel}
            aria-label="Discard transcript"
            data-testid="voice-discard"
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-ink hover:border-red-200 hover:text-red-700"
          >
            Discard
          </button>
        )}
      </div>

      {/* Persistent indicator: visible for the whole time the mic is live. */}
      {recording && (
        <p
          data-testid="voice-indicator"
          className="flex items-center gap-2 text-sm font-medium text-red-700"
        >
          <span
            aria-hidden="true"
            data-testid="voice-indicator-dot"
            className="inline-block h-2.5 w-2.5 animate-pulse rounded-full bg-red-600"
          />
          Recording — the microphone is live
        </p>
      )}

      {busy && (
        <p className="flex items-center gap-2 text-sm text-ink-muted" role="status">
          <span
            aria-hidden="true"
            className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-brand-100 border-t-brand-600"
          />
          {PHASE_MESSAGE[phase]}
        </p>
      )}

      {/* Transcript preview: editable, and nothing is submitted without the user. */}
      {phase === 'success' && (
        <div className="space-y-2 rounded-xl border border-slate-200 bg-white p-3">
          <label htmlFor="voice-transcript" className="block text-xs font-semibold text-ink">
            Transcript — review or edit before asking
          </label>
          <textarea
            id="voice-transcript"
            data-testid="voice-transcript"
            value={transcript}
            onChange={(event) => setTranscript(event.target.value)}
            rows={3}
            className="w-full resize-y rounded-lg border border-slate-200 px-3 py-2 text-sm text-ink focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
          />
          <button
            type="button"
            onClick={handleUseTranscript}
            disabled={transcript.trim().length === 0}
            data-testid="voice-use-transcript"
            className="rounded-xl bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Use this text
          </button>
        </div>
      )}

      {phase === 'error' && failure && (
        <p
          data-testid="voice-error"
          data-failure-kind={failure.kind}
          role="alert"
          className="text-sm text-red-700"
        >
          {failure.message}
        </p>
      )}

      {/* One live region announces every state change to screen readers. */}
      <p role="status" aria-live="polite" className="sr-only" data-testid="voice-status">
        {phase === 'error' && failure ? failure.message : PHASE_MESSAGE[phase]}
      </p>
    </div>
  );
}

