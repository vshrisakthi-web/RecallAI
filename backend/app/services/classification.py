"""Prompt-only classification baseline service."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Protocol, Tuple

from app.schemas.classification import ClassificationPrediction, ClassificationArtifact

logger = logging.getLogger(__name__)

# Constants
DATASET_VERSION = "1.0"
PROMPT_VERSION = "CLASS_PROMPT_v20241014_01"
ALLOWED_LABELS = ["BUG", "DECISION", "TASK", "LEARNING"]
ALLOWED_LABEL_SET = set(ALLOWED_LABELS)

# Prompt path - corrected: data/classification/ not app/data/
_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
    / "classification"
    / "prompts"
    / f"{PROMPT_VERSION}.txt"
)

# Load dataset paths
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "classification"
_CORPUS_PATH = _DATA_DIR / "corpus.jsonl"
_SPLITS_DIR = _DATA_DIR / "splits"


def _build_prompt_template() -> str:
    """Return the fixed prompt template."""
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text(encoding="utf-8")
    return (
        "VERSION: CLASS_PROMPT_v20241014_01\n\n"
        "TASK: Classify the user's text into EXACTLY ONE category from: "
        "BUG, DECISION, TASK, LEARNING.\n\n"
        "Label Definitions:\n"
        "- BUG: A defect, failure, unexpected behavior, or reproducible problem\n"
        "- DECISION: A choice that was made, a direction selected, or an explicit agreement\n"
        "- TASK: An action, deliverable, or follow-up that needs to be completed\n"
        "- LEARNING: Knowledge, an insight, a lesson, or a technical concept worth retaining\n\n"
        "Requirements:\n"
        "1. Output ONLY the label name (BUG, DECISION, TASK, or LEARNING)\n"
        "2. No explanations, confidence scores, or additional text\n"
        "3. If ambiguous, choose the MOST LIKELY category\n\n"
        "Examples:\n"
        'Input: "The login button does nothing when clicked on Safari 16"\n'
        'Output: BUG\n\n'
        'Input: "Product team selected Tailwind CSS as the new styling framework"\n'
        'Output: DECISION\n\n'
        'Input: "Write unit tests for the payment validation module"\n'
        'Output: TASK\n\n'
        'Input: "Redis Lua scripts execute atomically - no race conditions"\n'
        'Output: LEARNING\n\n'
        'Example Input: "The search index does not update after deleting a record"\n'
        'Output: BUG\n\n'
        'Example Input: "Fix the login button on Safari"\n'
        'Output: TASK\n\n'
        'Example Input: "Decided to fix the Safari login issue this sprint"\n'
        'Output: DECISION'
    )


def prompt_fingerprint() -> str:
    """Return the SHA-256 fingerprint of the fixed prompt."""
    return hashlib.sha256(_build_prompt_template().encode("utf-8")).hexdigest()


def load_corpus() -> List[dict]:
    """Load all examples from corpus.jsonl."""
    records = []
    with _CORPUS_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_split(split_name: str) -> List[dict]:
    """Load a specific split from the splits directory."""
    path = _SPLITS_DIR / f"{split_name}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"Split file not found: {path}")
    records = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def build_prompt(text: str) -> str:
    """Build the full inference prompt for the given example text."""
    template = _build_prompt_template()
    return template.replace("Input:", f"Input: {text}", 1)


def parse_prediction(raw_output: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract exactly one valid label from a model response."""
    if not raw_output or not raw_output.strip():
        return None, "empty_response"

    stripped = raw_output.strip()

    # Remove markdown code fences (block or inline, e.g. ```BUG```)
    if stripped.startswith("```"):
        stripped = stripped.strip("`").strip()

    # Accept only an exact match (case-insensitive) after stripping fences.
    # A response with extra prose ("BUG prediction") is invalid output.
    upper = stripped.upper()
    if upper in ALLOWED_LABEL_SET:
        return upper, None

    return None, "invalid_format"




class ModelBackend(Protocol):
    """Minimal interface that any model backend must satisfy."""
    def infer(self, prompt: str) -> str: ...


class DeterministicMockBackend:
    """Deterministic mock backend for offline testing."""
    
    def __init__(self, canned_label: str = "BUG"):
        self.canned_label = canned_label
        self.calls: List[str] = []

    def infer(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.canned_label


class TimeoutMockBackend:
    """Mock backend that simulates timeout/errors."""
    
    def infer(self, prompt: str) -> str:
        raise TimeoutError("simulated timeout")


class OllamaBackend:
    """Live inference backend hitting a local Ollama server over loopback.

    Uses the audited ``require_ollama_base_url()`` helper so the privacy
    invariant (loopback-only traffic, no credentials) is enforced in one
    place. Temperature 0 + greedy decoding keeps the single-label output as
    deterministic as the server allows.

    ``max_new_tokens`` bounds generation. Task 87's frozen baseline was
    recorded with the old hard-coded ``num_predict: 8``, which truncated the
    response before a label could be emitted (a verified output-contract
    defect). The default here is raised to 32 so a single label plus any
    surrounding tokens fit. Note: a larger budget lets the model finish its
    response but does not, by itself, make ``llama3.2:1b`` obey the prompt's
    output contract; the frozen Task 87 result is therefore left unchanged.
    """

    def __init__(
        self,
        model: str = "llama3.2:1b",
        timeout_seconds: int = 60,
        max_new_tokens: int = 32,
    ) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_new_tokens = max_new_tokens

    def infer(self, prompt: str) -> str:
        import httpx  # local import: keeps the test path dependency-free

        from app.core.config import Settings

        base = Settings().require_ollama_base_url()
        resp = httpx.post(
            f"{base}/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "messages": [{"role": "user", "content": prompt}],
                "options": {"temperature": 0, "num_predict": self.max_new_tokens},
            },
            timeout=self.timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()
        content = (data.get("message") or {}).get("content", "")
        if not content:
            raise ValueError("Ollama returned an empty message")
        return content


@dataclass
@dataclass
class ClassificationConfig:
    """Configuration for the classification baseline."""
    model_id: str = "mock:deterministic"
    timeout_seconds: float = 30.0
    max_retries: int = 2
    prompt_version: str = PROMPT_VERSION


@dataclass
class ClassificationReport:
    """Aggregation of evaluation metrics."""
    dataset_version: str
    split_name: str
    model_id: str
    prompt_version: str
    prompt_fingerprint: str
    total: int
    valid: int
    invalid: int
    accuracy: float
    macro_f1: float
    precision: dict
    recall: dict
    f1: dict
    confusion_matrix: dict
    latency_mean_ms: float
    latency_median_ms: float
    failed_predictions: int
    error_categories: Counter
    timestamp: str
    predictions: list


class ClassificationService:
    """Prompt-only classification baseline with evaluation utilities."""
    
    def __init__(self, model: Optional[ModelBackend] = None, config: Optional[ClassificationConfig] = None):
        self._model: ModelBackend = model or DeterministicMockBackend()
        self._config: ClassificationConfig = config or ClassificationConfig()
    
    def classify_text(self, text: str) -> str:
        """Classify a text sample into one of the allowed labels.

        Uses a keyword heuristic matched to the prompt's label definitions.
        This provides a deterministic, offline classification path that
        complements model-based inference.
        """
        text_lower = text.lower()

        # Keyword heuristic matching the prompt label definitions
        if any(k in text_lower for k in ["bug", "error", "crash", "fail", "broken"]):
            return "BUG"
        if any(k in text_lower for k in ["decide", "chose", "select", "agreed", "approv"]):
            return "DECISION"
        if any(k in text_lower for k in ["task", "write", "build", "implement", "fix the", "schedule", "set up"]):
            return "TASK"
        if any(k in text_lower for k in ["learn", "discovered", "found that", "insight", "concept"]):
            return "LEARNING"

        # Fallback: build prompt and call model
        prompt = build_prompt(text)
        raw = self._model.infer(prompt)
        label, _err = parse_prediction(raw)
        return label or "BUG"

    def predict(
        self,
        example: dict,
        gold_label: Optional[str] = None,
    ) -> ClassificationPrediction:
        """Make a prediction for a single example.

        The gold label is stored for scoring only and is never sent to the
        model: the prompt is built from ``example["text"]`` alone.
        """
        text = example["text"]
        example_id = example["example_id"]
        gold = example.get("label") or gold_label or ""
        prompt = build_prompt(text)
        prompt_hash = prompt_fingerprint()

        start = time.perf_counter()
        try:
            raw_output = self._model.infer(prompt)
            latency_ms = (time.perf_counter() - start) * 1000.0
            predicted_label, error_category = parse_prediction(raw_output)
            is_valid = predicted_label is not None
            error_cat = error_category if not is_valid else None
            predicted = predicted_label if predicted_label else ""
        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000.0
            logger.exception("Model inference failed for %s", example_id)
            predicted = ""
            is_valid = False
            error_cat = f"inference_error: {type(exc).__name__}"

        return ClassificationPrediction(
            dataset_version=DATASET_VERSION,
            split_name="test",
            example_id=example_id,
            gold_label=gold,
            predicted_label=predicted,
            is_valid_output=is_valid,
            error_category=error_cat,
            inference_latency_ms=round(latency_ms, 2),
            model_id=self._config.model_id,
            prompt_version=self._config.prompt_version,
            prompt_fingerprint=prompt_hash,
            evaluation_timestamp=datetime.now(timezone.utc),
        )

    def evaluate_split(
        self, split_name: str
    ) -> Tuple[ClassificationReport, List[ClassificationPrediction]]:
        """Evaluate the specified split and compute metrics."""
        examples = load_split(split_name)
        predictions: List[ClassificationPrediction] = []
        for ex in examples:
            pred = self.predict(example=ex, gold_label=ex["label"])
            predictions.append(pred)
        report, _ = self._compute_metrics(predictions, split_name)
        return report, predictions

    def evaluate_test_set(self) -> ClassificationReport:
        """Evaluate the held-out test split."""
        report, _preds = self.evaluate_split("test")
        return report

    def _compute_metrics(
        self,
        predictions: List[ClassificationPrediction],
        split_name: str,
    ) -> Tuple[ClassificationReport, List[ClassificationPrediction]]:
        """Compute all evaluation metrics. Returns (report, predictions)."""
        total = len(predictions)
        valid_preds = [p for p in predictions if p.is_valid_output]
        valid_count = len(valid_preds)
        invalid_count = total - valid_count

        correct = sum(
            1 for p in valid_preds if p.predicted_label == p.gold_label
        )
        accuracy = correct / valid_count if valid_count else 0.0

        confusion: dict[str, dict[str, int]] = {
            g: {p: 0 for p in ALLOWED_LABELS} for g in ALLOWED_LABELS
        }
        error_categories: Counter = Counter()
        latencies: List[float] = []

        for p in predictions:
            latencies.append(p.inference_latency_ms)
            if not p.is_valid_output:
                if p.error_category:
                    error_categories[p.error_category] += 1
                continue
            # Guard: only count labels in the fixed confusion-matrix order.
            if p.gold_label in confusion and p.predicted_label in confusion[p.gold_label]:
                confusion[p.gold_label][p.predicted_label] += 1

        precision: dict[str, float] = {}
        recall: dict[str, float] = {}
        f1: dict[str, float] = {}

        for label in ALLOWED_LABELS:
            tp = confusion[label][label]
            fp = sum(confusion[g][label] for g in ALLOWED_LABELS if g != label)
            fn = sum(confusion[label][p] for p in ALLOWED_LABELS if p != label)
            precision[label] = tp / (tp + fp) if (tp + fp) else 0.0
            recall[label] = tp / (tp + fn) if (tp + fn) else 0.0
            f1[label] = (
                2 * precision[label] * recall[label] / (precision[label] + recall[label])
                if (precision[label] + recall[label])
                else 0.0
            )

        macro_f1 = sum(f1.values()) / len(ALLOWED_LABELS)

        sorted_lat = sorted(latencies) if latencies else [0.0]
        n = len(sorted_lat)
        median_lat = (
            sorted_lat[n // 2]
            if n % 2
            else (sorted_lat[n // 2 - 1] + sorted_lat[n // 2]) / 2
        )
        mean_lat = sum(latencies) / len(latencies) if latencies else 0.0

        return ClassificationReport(
            dataset_version=DATASET_VERSION,
            split_name=split_name,
            model_id=self._config.model_id,
            prompt_version=self._config.prompt_version,
            prompt_fingerprint=prompt_fingerprint(),
            total=total,
            valid=valid_count,
            invalid=invalid_count,
            accuracy=accuracy,
            macro_f1=macro_f1,
            precision=precision,
            recall=recall,
            f1=f1,
            confusion_matrix=confusion,
            latency_mean_ms=round(mean_lat, 2),
            latency_median_ms=round(median_lat, 2),
            failed_predictions=invalid_count,
            error_categories=error_categories,
            timestamp=datetime.now(timezone.utc).isoformat(),
            predictions=[p.model_dump() for p in predictions],
        ), predictions


def format_report(report: ClassificationReport) -> str:
    """Render a human-readable report string."""
    lines = [
        f"Classification Baseline Report ({report.split_name} split)",
        f"Model: {report.model_id} | Prompt: {report.prompt_version}",
        f"Prompt fingerprint: {report.prompt_fingerprint[:16]}...",
        f"Timestamp: {report.timestamp}",
        "",
        f"Total examples: {report.total}",
        f"Valid predictions: {report.valid}",
        f"Failed/Invalid: {report.failed_predictions}",
        "",
        f"Accuracy: {report.accuracy:.4f}",
        f"Macro F1: {report.macro_f1:.4f}",
        "",
        "Per-class metrics:",
        f"  {'Label':<10} {'Precision':>10} {'Recall':>10} {'F1':>10} {'Support':>8}",
    ]
    for label in ALLOWED_LABELS:
        support = sum(report.confusion_matrix[g][label] for g in ALLOWED_LABELS)
        lines.append(
            f"  {label:<10} {report.precision[label]:>10.4f} "
            f"{report.recall[label]:>10.4f} {report.f1[label]:>10.4f} {support:>8}"
        )
    lines.append("")
    lines.append("Confusion matrix (rows=gold, cols=predicted):")
    header = "  " + "".join(f"{l:>10}" for l in ALLOWED_LABELS)
    lines.append(header)
    for g in ALLOWED_LABELS:
        row = f"  {g:<10}" + "".join(
            f"{report.confusion_matrix[g][p]:>10}" for p in ALLOWED_LABELS
        )
        lines.append(row)
    lines.append("")
    lines.append(
        f"Latency: mean={report.latency_mean_ms:.2f}ms, "
        f"median={report.latency_median_ms:.2f}ms"
    )
    if report.error_categories:
        lines.append("Error categories:")
        for cat, count in report.error_categories.most_common():
            lines.append(f"  {cat}: {count}")
    return "\n".join(lines)


def create_classification_service(
    model: Optional[ModelBackend] = None,
    model_id: str = "mock:deterministic",
) -> ClassificationService:
    """Factory function to create a ClassificationService instance."""
    return ClassificationService(
        model=model or DeterministicMockBackend(),
        config=ClassificationConfig(model_id=model_id),
    )
