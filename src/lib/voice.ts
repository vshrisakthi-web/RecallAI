/**
 * Voice capture seam (Module 9, Task 81).
 *
 * Plain English: the microphone UI must be testable *before* any real speech
 * recognition exists, and RecallAI is privacy-first, so audio capture is an
 * explicit, cancellable, releasable operation rather than a background stream.
 *
 * Two boundaries are defined here, and neither knows about the other:
 *
 *   AudioRecorder — owns the microphone. Produces an audio `Blob`. It never
 *                   touches a network and keeps no audio after `stop()`.
 *   Transcriber    — turns that `Blob` into text. In Task 81 this is always a
 *                   test double; Task 82 supplies the real backend service.
 *
 * Keeping them apart means the recording states (idle / recording / processing
 * / success / error) can be exercised deterministically in jsdom, where
 * `navigator.mediaDevices` and `MediaRecorder` do not exist.
 *
 * Privacy posture (Task 81; enforced in full by Task 85):
 *   * Recording starts only because the user pressed a button.
 *   * Nothing is recorded on mount, and a cancelled or unmounted recording
 *     releases the microphone immediately.
 *   * Audio lives only in memory as a `Blob`; nothing is written to disk and
 *     nothing is retained after `stop()`.
 */

/** The microphone UI lifecycle. Every visual state maps to exactly one of these. */
export type VoicePhase =
  | 'idle'
  /** `getUserMedia` is in flight — the browser may still show a permission prompt. */
  | 'requesting-permission'
  /** The microphone is live and audio is being captured. */
  | 'recording'
  /** Audio captured; transcription is in flight. */
  | 'processing'
  /** A transcript is available for preview/edit. */
  | 'success'
  /** Something failed. `failure` explains what, in user-facing language. */
  | 'error';

/** Why a voice interaction failed. A closed set, so the UI never guesses. */
export type VoiceFailureKind =
  /** The user (or browser policy) denied microphone access. */
  | 'permission-denied'
  /** No usable input device, or the device could not be opened. */
  | 'device-unavailable'
  /** This browser has no microphone capture support at all. */
  | 'not-supported'
  /** The user stopped before any audio was captured. */
  | 'no-audio'
  /** The recording was accepted but contained no intelligible speech. */
  | 'no-speech'
  /** The transcription service is not wired up yet (Task 82 replaces this). */
  | 'not-connected'
  /** Transcription was attempted and failed. */
  | 'transcription-failed'
  /** Anything unexpected, described but never leaking internals. */
  | 'unknown';

export interface VoiceFailure {
  kind: VoiceFailureKind;
  /** Safe, user-facing sentence. Never a stack trace or browser internals. */
  message: string;
}

/** A transcript plus the metadata the UI may show alongside it. */
export interface TranscriptResult {
  transcript: string;
  /** Wall-clock milliseconds spent transcribing, when the provider reports it. */
  processingMs?: number;
}

/**
 * Owns the microphone.
 *
 * `start()` resolves once audio is actually flowing, so the UI can move to
 * `recording` only when that is true. It rejects with a `VoiceFailure` rather
 * than a raw `DOMException`, so permission denial and a missing device are
 * distinguishable without inspecting browser error codes in the component.
 */
export interface AudioRecorder {
  start(): Promise<void>;
  /** Stop capturing and return the recorded audio. */
  stop(): Promise<Blob>;
  /** Abandon the recording and release the microphone. Always safe to call. */
  cancel(): void;
}

/** Turns recorded audio into text. A test double stands in until Task 82. */
export interface Transcriber {
  transcribe(audio: Blob): Promise<TranscriptResult>;
}

/** Builds a recorder, or returns null when the browser cannot record at all. */
export type RecorderFactory = () => AudioRecorder | null;

/**
 * The placeholder transcriber used until Task 82 connects a real service.
 *
 * It fails loudly instead of returning invented text: a privacy-first assistant
 * must never present a fabricated transcript as something the user said.
 */
export const notConnectedTranscriber: Transcriber = {
  async transcribe(): Promise<TranscriptResult> {
    throw {
      kind: 'not-connected',
      message: 'Voice transcription is not connected yet.',
    } satisfies VoiceFailure;
  },
};

/** MIME types to prefer, best first. Safari records MP4/AAC; Chrome/Firefox WebM/Opus. */
const PREFERRED_MIME_TYPES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/mp4',
  'audio/ogg;codecs=opus',
];

/** Maps a `getUserMedia` rejection onto a safe, specific `VoiceFailure`. */
export function mapRecorderError(error: unknown): VoiceFailure {
  const name =
    typeof error === 'object' && error !== null && 'name' in error
      ? String((error as { name?: unknown }).name)
      : '';

  if (
    name === 'NotAllowedError' ||
    name === 'PermissionDeniedError' ||
    name === 'SecurityError'
  ) {
    return {
      kind: 'permission-denied',
      message:
        'Microphone access was blocked. Allow it in your browser settings to use voice input.',
    };
  }
  if (
    name === 'NotFoundError' ||
    name === 'DevicesNotFoundError' ||
    name === 'NotReadableError' ||
    name === 'OverconstrainedError' ||
    name === 'AbortError'
  ) {
    return {
      kind: 'device-unavailable',
      message: 'No microphone is available. Connect one and try again.',
    };
  }
  return {
    kind: 'unknown',
    message: 'The microphone could not be started. Please try again.',
  };
}

/** Picks the first MIME type this browser can actually record. */
function pickMimeType(): string | undefined {
  const supports = (MediaRecorder as unknown as {
    isTypeSupported?: (type: string) => boolean;
  }).isTypeSupported;
  if (typeof supports !== 'function') return undefined;
  return PREFERRED_MIME_TYPES.find((type) => {
    try {
      return supports.call(MediaRecorder, type);
    } catch {
      return false;
    }
  });
}

/**
 * `MediaRecorder`-backed recorder.
 *
 * Feature-detects rather than assuming: in jsdom both `mediaDevices` and
 * `MediaRecorder` are absent, which is exactly the "unsupported browser" case
 * the UI must report instead of crashing.
 */
class MediaRecorderAudioRecorder implements AudioRecorder {
  private stream: MediaStream | null = null;
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];

  constructor(private readonly mediaDevices: MediaDevices) {}

  async start(): Promise<void> {
    if (this.recorder) {
      throw {
        kind: 'unknown',
        message: 'The microphone is already recording.',
      } satisfies VoiceFailure;
    }

    let stream: MediaStream;
    try {
      // The user has already acted; ask for audio only, never video.
      stream = await this.mediaDevices.getUserMedia({ audio: true });
    } catch (error) {
      throw mapRecorderError(error);
    }

    const mimeType = pickMimeType();
    let recorder: MediaRecorder;
    try {
      recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    } catch (error) {
      // Release the mic immediately: a failed recorder must not hold it open.
      stream.getTracks().forEach((track) => track.stop());
      throw mapRecorderError(error);
    }

    const chunks: Blob[] = [];
    recorder.ondataavailable = (event: BlobEvent) => {
      if (event.data && event.data.size > 0) chunks.push(event.data);
    };

    this.stream = stream;
    this.recorder = recorder;
    this.chunks = chunks;
    // A small timeslice flushes data even if the tab is torn down mid-recording.
    recorder.start(250);
  }

  async stop(): Promise<Blob> {
    const recorder = this.recorder;
    if (!recorder) {
      throw {
        kind: 'no-audio',
        message: 'Nothing was recorded.',
      } satisfies VoiceFailure;
    }

    const stopped = new Promise<void>((resolve) => {
      recorder.onstop = () => resolve();
    });

    try {
      recorder.stop();
    } catch (error) {
      this.cleanup();
      throw mapRecorderError(error);
    }
    await stopped;

    const chunks = this.chunks;
    const type = recorder.mimeType || chunks[0]?.type || 'audio/webm';
    const audio = new Blob(chunks, { type });
    this.cleanup();

    if (audio.size === 0) {
      throw {
        kind: 'no-audio',
        message: 'Nothing was recorded — try holding the microphone button longer.',
      } satisfies VoiceFailure;
    }
    return audio;
  }

  cancel(): void {
    const recorder = this.recorder;
    this.cleanup();
    if (!recorder) return;
    try {
      // Detach handlers first so a cancelled recording can never resolve a
      // pending stop() with a half-written blob.
      recorder.onstop = null;
      recorder.ondataavailable = null;
      recorder.stop();
    } catch {
      // Cancelling an already-stopped recorder is fine; nothing to do.
    }
  }

  /** Releases the microphone. Media tracks are the real resource; drop them. */
  private cleanup(): void {
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    this.recorder = null;
    this.chunks = [];
  }
}

/**
 * Create the browser recorder, or `null` when this environment cannot record.
 *
 * Feature detection happens here — never at module load — so importing this
 * module in a test environment is always safe.
 */
export const createMediaRecorder: RecorderFactory = () => {
  if (typeof navigator === 'undefined' || typeof MediaRecorder === 'undefined') return null;
  const mediaDevices = navigator.mediaDevices;
  if (!mediaDevices || typeof mediaDevices.getUserMedia !== 'function') return null;
  return new MediaRecorderAudioRecorder(mediaDevices);
};

