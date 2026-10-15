"""Speech-to-text worker that runs inside the isolated voice venv (Task 82).

This module is deliberately *not* under ``app/``: it must only ever be imported
by ``.venv-voice``'s interpreter (which has faster-whisper installed), never by
the FastAPI app (whose venv does not). The app talks to it as a subprocess over
a one-shot JSON protocol:

    python voice/transcribe_worker.py <audio_path> <model_name>

stdout carries exactly one JSON object on success::

    {"ok": true, "text": "...", "language": "en",
     "duration_seconds": 2.31, "model": "base"}

or on a classified failure::

    {"ok": false, "kind": "invalid-audio" | "model-load-failed" | "no-speech" | "worker-error",
     "message": "safe, user-readable text"}

Design rules, matching the backend's privacy posture:

* The transcript goes to stdout only — it is never logged, and argv/stderr
  carry no speech content (argv is just the temp path and model name).
* Exit code is 0 only for ``ok: true``; every failure exits 1 so a crashed or
  hung worker can never be mistaken for a transcript.
* Decoding is in-Python (soundfile, then PyAV): no system ffmpeg is assumed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _emit(payload: dict) -> None:
    json.dump(payload, sys.stdout)
    sys.stdout.write("\n")
    sys.stdout.flush()


def _decode_audio(path: Path):
    """Decode to mono float32 at the sample rate the model expects (16 kHz).

    Tries soundfile first (wav/flac/ogg — the cheap native path), then PyAV
    (webm/opus and mp4/AAC — exactly what browser MediaRecorder produces).
    Both run from bundled libraries, so no ffmpeg binary is required.
    """
    import numpy as np

    try:
        import soundfile as sf

        data, rate = sf.read(str(path), dtype="float32", always_2d=True)
        samples = data.mean(axis=1)
    except Exception:
        samples, rate = None, None  # noqa: SIM108 — fall through to PyAV

    if samples is None:
        import av

        with av.open(str(path)) as container:
            stream = next((s for s in container.streams if s.type == "audio"), None)
            if stream is None:
                raise ValueError("the file contains no audio stream")
            rate = stream.codec_context.sample_rate or 16_000
            chunks = []
            for frame in container.decode(stream):
                chunks.append(frame.to_ndarray().astype("float32", copy=False))
        if not chunks:
            raise ValueError("the audio stream is empty")
        stacked = np.concatenate(chunks, axis=-1)
        if stacked.ndim == 1:
            samples = stacked
        else:
            # Planar decoders yield (channels, samples); packed ones yield
            # (samples, channels). Channels are always the small axis (<= 32),
            # so downmix on whichever side is small rather than assuming.
            channel_axis = 0 if stacked.shape[0] <= 32 else 1
            samples = stacked.mean(axis=channel_axis)

    if samples.size == 0:
        raise ValueError("the audio is empty")

    # Resample to 16 kHz mono if needed (Whisper-family models expect it).
    if rate != 16_000:
        from numpy import interp

        duration = samples.shape[0] / float(rate)
        target_len = max(int(duration * 16_000), 1)
        x_old = np.linspace(0.0, duration, num=samples.shape[0], endpoint=False)
        x_new = np.linspace(0.0, duration, num=target_len, endpoint=False)
        samples = interp(x_new, x_old, samples).astype("float32")
    return samples


def main(argv: list[str]) -> int:
    """Run one transcription request; returns the process exit code.

    Exit codes: 0 success, 2 classified failure (JSON emitted), 3 unexpected
    worker error (JSON emitted when possible). The app treats any non-zero
    exit as a failure, so a crash can never be mistaken for a transcript.
    """
    if len(argv) != 4:
        _emit(
            {
                "ok": False,
                "kind": "worker-error",
                "message": "The transcription worker was invoked incorrectly.",
            }
        )
        return 3

    audio_path = Path(argv[1])
    model_name = argv[2]
    try:
        max_seconds = float(argv[3])
    except ValueError:
        _emit(
            {
                "ok": False,
                "kind": "worker-error",
                "message": "The transcription worker was invoked incorrectly.",
            }
        )
        return 3

    if not audio_path.is_file():
        _emit(
            {
                "ok": False,
                "kind": "invalid-audio",
                "message": "The uploaded audio could not be read.",
            }
        )
        return 2

    # Decode before anything expensive: oversized or corrupt audio is rejected
    # without ever loading the model.
    try:
        samples = _decode_audio(audio_path)
    except Exception:
        # Includes ValueError (empty/malformed) and decoder errors. Decoder
        # messages can quote internal paths, so only a fixed message ships.
        _emit(
            {
                "ok": False,
                "kind": "invalid-audio",
                "message": "The file is not a readable audio recording.",
            }
        )
        return 2

    duration_seconds = float(samples.shape[0]) / 16_000.0
    if duration_seconds > max_seconds:
        _emit(
            {
                "ok": False,
                "kind": "too-long",
                "message": (
                    "The recording is longer than the "
                    f"{max_seconds:.0f}-second limit. Please ask a shorter question."
                ),
            }
        )
        return 2

    try:
        from faster_whisper import WhisperModel

        model = WhisperModel(model_name, device="cpu", compute_type="int8")
    except Exception:
        _emit(
            {
                "ok": False,
                "kind": "model-load-failed",
                "message": (
                    "The speech model could not be loaded. Run the one-time "
                    "setup in docs/module-9-voice.md to download it."
                ),
            }
        )
        return 2

    try:
        segments, info = model.transcribe(samples, beam_size=1, vad_filter=True)
        text = " ".join(segment.text.strip() for segment in segments).strip()
    except Exception:
        _emit(
            {
                "ok": False,
                "kind": "worker-error",
                "message": "The recording could not be transcribed.",
            }
        )
        return 3

    if not text:
        _emit(
            {
                "ok": False,
                "kind": "no-speech",
                "message": "No speech was detected in the recording.",
            }
        )
        return 2

    _emit(
        {
            "ok": True,
            "text": text,
            "language": info.language,
            "duration_seconds": round(duration_seconds, 2),
            "model": model_name,
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

