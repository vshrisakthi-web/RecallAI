"""Frozen prompt-only classification baseline runner (Task 87).

Reads the held-out 12-example test split, classifies each example with the
locally installed Ollama chat model ``llama3.2:1b`` over loopback, and writes
one prediction artifact per example plus machine- and human-readable reports
under ``data/classification/results/``.

Contract
--------
* The prompt is fixed and versioned; it is never tuned against this test
  split and is loaded from ``data/classification/prompts/CLASS_PROMPT_v20241014_01.txt``.
* Gold labels are stored for scoring only and are never included in the
  inference prompt.
* Only the example's own text is passed to the model.
* Each model output is validated to be exactly one allowed label
  (BUG, DECISION, TASK, or LEARNING); anything else is recorded as invalid.
* Failed requests and invalid outputs are counted and reported explicitly.
"""

from __future__ import annotations

import json
import dataclasses
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Resolve paths relative to this script so the runner works from any cwd.
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "classification"
RESULTS_DIR = DATA_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

MODEL_ID = "llama3.2:1b"
MODEL_TIMEOUT_SECONDS = 120
MAX_RETRIES = 2

# Guarantee ``backend`` (and therefore the ``app`` package) is importable,
# regardless of how this script is launched (direct execution or ``-m``).
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Reuse the repository's own Ollama wiring (loopback-only + auth-free).
from app.core.config import Settings  # noqa: E402  # type: ignore  # pyright: ignore[reportUnsupportedDunderAll]
from app.services.classification import (  # noqa: E402
    ALLOWED_LABELS,
    ClassificationReport,
    ClassificationService,
    OllamaBackend,
    format_report,
    load_split,
    prompt_fingerprint,
    create_classification_service,
    PROMPT_VERSION,
)

def _ollama_reachable() -> bool:
    """Light-touch check that the local Ollama chat endpoint answers."""
    base = Settings().require_ollama_base_url()
    try:
        import httpx

        resp = httpx.get(f"{base}/api/tags", timeout=5.0)
        resp.raise_for_status()
        return True
    except Exception as exc:  # pragma: no cover - environment dependent
        print(f"[runner] Ollama unavailable at {base}: {exc}", file=sys.stderr)
        return False


def _json_default(obj: Any) -> Any:
    """Serialize values the standard json module cannot handle on its own."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _run_once() -> dict[str, Any]:
    """Run the frozen baseline once and write all three artifacts."""
    if not _ollama_reachable():
        sys.exit("BLOCKED: local Ollama chat endpoint is not reachable.")

    examples = load_split("test")
    svc = create_classification_service(
        model=OllamaBackend(
            model=MODEL_ID,
            timeout_seconds=MODEL_TIMEOUT_SECONDS,
        ),
        model_id=MODEL_ID,
    )

    report, predictions = svc.evaluate_split("test")

    predictions_path = RESULTS_DIR / "baseline_predictions.jsonl"
    with predictions_path.open("w", encoding="utf-8") as handle:
        for pred in predictions:
            handle.write(json.dumps(pred.model_dump(mode="json"), ensure_ascii=False) + "\n")

    report_path = RESULTS_DIR / "baseline_report.json"
    with report_path.open("w", encoding="utf-8") as handle:
        report_payload = dataclasses.asdict(report)
        # NOTE: Python 3.9's dataclasses.asdict() mangles dict subclasses
        # (e.g. Counter) by rebuilding them from their items, so
        # {label: count} can come out as {('label', count): 1}.
        # Rebuild the plain dict from the service object (its keys are the
        # real label strings). Also serialize the Pydantic prediction models.
        report_payload["error_categories"] = dict(report.error_categories)
        report_payload["predictions"] = report.predictions
        json.dump(report_payload, handle, indent=2, ensure_ascii=False, default=_json_default)

    report_text_path = RESULTS_DIR / "baseline_report.txt"
    report_text_path.write_text(
        "Classification Baseline Report\n"
        "==============================\n\n"
        + format_report(report)
        + "\n\n"
        + f"Run timestamp: {report.timestamp}\n"
        + f"Prompt fingerprint: {report.prompt_fingerprint}\n"
        + f"Platform: {platform.system()} {platform.release()} "
        f"(Python {platform.python_version()})\n"
        + f"Inputs: {len(predictions)} examples, "
        f"{report.valid} valid, {report.invalid} invalid\n"
        + "NOTE: the held-out test set contains only ONE TASK example; "
        + "TASK-specific precision/recall/F1 are therefore highly uncertain.\n",
        encoding="utf-8",
    )

    return {
        "report": report,
        "predictions": predictions,
        "predictions_path": str(predictions_path),
        "report_path": str(report_path),
        "report_text_path": str(report_text_path),
    }


def main() -> None:
    print(f"Task 87 frozen baseline: {MODEL_ID} over loopback")
    print(f"Prompt: {PROMPT_VERSION} ({prompt_fingerprint()[:12]}...)")
    print(f"Test split examples: {len(load_split('test'))}")
    print("Running a single frozen evaluation pass...\n")

    result = _run_once()

    report = result["report"]
    print("=" * 60)
    print(f"Accuracy : {report.accuracy:.4f}")
    print(f"Macro F1 : {report.macro_f1:.4f}")
    print(f"Valid    : {report.valid}")
    print(f"Invalid  : {report.invalid}")
    print(f"Failed   : {report.failed_predictions}")
    print(f"Latency  : mean {report.latency_mean_ms:.2f}ms, "
          f"median {report.latency_median_ms:.2f}ms")
    print("=" * 60)
    print("Per-class F1: "
          + ", ".join(f"{label}={report.f1[label]:.4f}"
                      for label in ALLOWED_LABELS))

    print("\nArtifacts written:")
    print(f"  {result['predictions_path']}")
    print(f"  {result['report_path']}")
    print(f"  {result['report_text_path']}")


if __name__ == "__main__":
    main()
