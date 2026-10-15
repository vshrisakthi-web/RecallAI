"""Task 89 focused tests: prompt-only baseline (Task 87) vs LoRA (Task 88).

All tests are deterministic and offline. They validate the metric policy,
input alignment, failure accounting, report schema, and reproducibility of the
Task 89 comparison without requiring torch/transformers or network access.
The heavy ML reload path (load_lora_model) is intentionally NOT exercised here;
real adapter evaluation is performed by running the script under .venv-ft.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.services.classification import ALLOWED_LABELS, PROMPT_VERSION, prompt_fingerprint
from app.scripts import evaluate_lora_vs_baseline as ev

LABEL_ORDER = ["BUG", "DECISION", "TASK", "LEARNING"]


def _pred(ex_id, gold, pred, valid, err=None, lat=100.0):
    return {
        "example_id": ex_id,
        "gold_label": gold,
        "predicted_label": pred,
        "is_valid_output": valid,
        "error_category": err,
        "inference_latency_ms": lat,
    }


# ---------------------------------------------------------------------------
# Metric policy
# ---------------------------------------------------------------------------
class TestMetricPolicy:
    def test_primary_accuracy_counts_invalid_as_wrong(self):
        # 4 examples: 1 correct valid, 1 wrong valid, 2 invalid.
        preds = [
            _pred("a", "BUG", "BUG", True),
            _pred("b", "BUG", "TASK", True),
            _pred("c", "BUG", "", False, "invalid_format"),
            _pred("d", "DECISION", "", False, "invalid_format"),
        ]
        m = ev.compute_comparison_metrics(preds)
        assert m["total"] == 4
        assert m["valid"] == 2
        assert m["invalid"] == 2
        assert m["correct"] == 1
        # PRIMARY: correct / total -> 1/4, NOT 1/2.
        assert m["primary_accuracy"] == pytest.approx(0.25)
        # SECONDARY: correct / valid -> 1/2.
        assert m["valid_accuracy"] == pytest.approx(0.5)

    def test_all_invalid_primary_zero_valid_none(self):
        # Task 87-like: zero valid predictions.
        preds = [_pred(f"x{i}", "BUG", "", False, "invalid_format") for i in range(12)]
        m = ev.compute_comparison_metrics(preds)
        assert m["valid"] == 0
        assert m["invalid"] == 12
        assert m["primary_accuracy"] == 0.0
        assert m["valid_accuracy"] is None
        assert m["error_categories"] == {"invalid_format": 12}
        assert m["macro_f1"] == 0.0

    def test_zero_division_classes_score_zero(self):
        # Only BUG predicted and gold; TASK has no gold support -> recall 0.0,
        # and classes never predicted -> precision 0.0 (no ZeroDivisionError).
        preds = [
            _pred("a", "BUG", "BUG", True),
            _pred("b", "BUG", "BUG", True),
        ]
        m = ev.compute_comparison_metrics(preds)
        assert m["precision"]["BUG"] == pytest.approx(1.0)
        assert m["recall"]["BUG"] == pytest.approx(1.0)
        assert m["precision"]["TASK"] == 0.0
        assert m["recall"]["TASK"] == 0.0
        assert m["f1"]["TASK"] == 0.0
        assert set(m["precision"]) == set(LABEL_ORDER)

    def test_fixed_label_order_and_confusion_shape(self):
        preds = [_pred("a", "LEARNING", "BUG", True)]
        m = ev.compute_comparison_metrics(preds)
        assert list(m["precision"].keys()) == LABEL_ORDER
        assert list(m["confusion_matrix"].keys()) == LABEL_ORDER
        for g in LABEL_ORDER:
            assert list(m["confusion_matrix"][g].keys()) == LABEL_ORDER
        # LEARNING gold predicted as BUG.
        assert m["confusion_matrix"]["LEARNING"]["BUG"] == 1

    def test_confusion_counts_only_valid(self):
        preds = [
            _pred("a", "BUG", "BUG", True),
            _pred("b", "BUG", "", False, "invalid_format"),
        ]
        m = ev.compute_comparison_metrics(preds)
        total_in_cm = sum(sum(row.values()) for row in m["confusion_matrix"].values())
        assert total_in_cm == 1  # invalid row excluded from matrix

    def test_latency_mean_median(self):
        preds = [
            _pred("a", "BUG", "BUG", True, lat=10.0),
            _pred("b", "BUG", "BUG", True, lat=20.0),
            _pred("c", "BUG", "BUG", True, lat=60.0),
        ]
        m = ev.compute_comparison_metrics(preds)
        assert m["latency_mean_ms"] == pytest.approx(30.0)
        assert m["latency_median_ms"] == pytest.approx(20.0)



# ---------------------------------------------------------------------------
# Input alignment + artifact handling
# ---------------------------------------------------------------------------
class TestInputAlignmentAndArtifacts:
    def test_both_systems_same_example_ids_and_gold(self):
        test_records = [{"example_id": f"e{i}", "text": "t", "label": "BUG"} for i in range(3)]
        base = [_pred(f"e{i}", "BUG", "", False, "invalid_format") for i in range(3)]
        lora = [_pred(f"e{i}", "BUG", "BUG", True) for i in range(3)]
        combined, report = ev.build_comparison(
            base, lora, test_records, "fp", "SmolLM2-135M",
            Path("/tmp/adapter"), None, "2024-01-01T00:00:00+00:00",
        )
        ids = [r["example_id"] for r in combined]
        assert ids == ["e0", "e1", "e2"]
        assert report["input_alignment"]["baseline_covers_all_example_ids"] is True
        assert report["input_alignment"]["lora_covers_all_example_ids"] is True
        for row in combined:
            assert row["gold_label"] == "BUG"
            assert row["task87"]["predicted_label"] == ""
            assert row["task88"]["predicted_label"] == "BUG"

    def test_missing_ids_flagged(self):
        test_records = [{"example_id": f"e{i}", "text": "t", "label": "BUG"} for i in range(3)]
        base = [_pred("e0", "BUG", "", False, "invalid_format")]  # missing e1, e2
        lora = [_pred(f"e{i}", "BUG", "BUG", True) for i in range(3)]
        _, report = ev.build_comparison(
            base, lora, test_records, "fp", "SmolLM2-135M",
            Path("/tmp/adapter"), None, "2024-01-01T00:00:00+00:00",
        )
        assert report["input_alignment"]["baseline_covers_all_example_ids"] is False
        assert report["input_alignment"]["missing_in_baseline"] == ["e1", "e2"]

    def test_report_has_required_sections(self):
        test_records = [{"example_id": "e0", "text": "t", "label": "BUG"}]
        base = [_pred("e0", "BUG", "", False, "invalid_format")]
        lora = [_pred("e0", "BUG", "BUG", True)]
        _, report = ev.build_comparison(
            base, lora, test_records, "fp", "SmolLM2-135M",
            Path("/tmp/adapter"), {"epochs": 2}, "2024-01-01T00:00:00+00:00",
        )
        for key in (
            "objective", "methodology", "metric_policy", "dataset_version",
            "label_order", "example_ids", "input_alignment",
            "task87_baseline", "task88_finetuned", "side_by_side",
            "confusion_matrices", "per_class", "latency", "inference_config",
            "reproducibility", "limitations", "task90_recommendation",
            "evaluation_timestamp",
        ):
            assert key in report, f"missing report key: {key}"
        assert report["label_order"] == LABEL_ORDER
        joined = " ".join(report["limitations"]).lower()
        assert "one task example" in joined
        assert "different base models" in joined

    def test_report_is_json_serializable(self):
        test_records = [{"example_id": "e0", "text": "t", "label": "BUG"}]
        base = [_pred("e0", "BUG", "", False, "invalid_format")]
        lora = [_pred("e0", "BUG", "BUG", True)]
        _, report = ev.build_comparison(
            base, lora, test_records, "fp", "SmolLM2-135M",
            Path("/tmp/adapter"), None, "2024-01-01T00:00:00+00:00",
        )
        s = json.dumps(report)
        assert '"primary_accuracy"' in s

    def test_format_report_text_runs_and_mentions_both(self):
        test_records = [{"example_id": "e0", "text": "t", "label": "BUG"}]
        base = [_pred("e0", "BUG", "", False, "invalid_format")]
        lora = [_pred("e0", "BUG", "BUG", True)]
        _, report = ev.build_comparison(
            base, lora, test_records, "fp", "SmolLM2-135M",
            Path("/tmp/adapter"), None, "2024-01-01T00:00:00+00:00",
        )
        text = ev.format_report_text(report)
        assert "Task 87" in text and "Task 88" in text
        assert "PRIMARY accuracy" in text

    def test_normalize_baseline_row(self):
        raw = {
            "example_id": "e0", "gold_label": "BUG", "predicted_label": "",
            "is_valid_output": False, "error_category": "invalid_format",
            "inference_latency_ms": 500.0,
        }
        row = ev.normalize_baseline_row(raw)
        assert row["example_id"] == "e0"
        assert row["is_valid_output"] is False
        assert row["inference_latency_ms"] == 500.0

    def test_prompt_fingerprint_matches_constant(self):
        assert PROMPT_VERSION == "CLASS_PROMPT_v20241014_01"
        assert prompt_fingerprint() == ev.prompt_fingerprint()


# ---------------------------------------------------------------------------
# Integration with real on-disk artifacts (read-only, no mutation)
# ---------------------------------------------------------------------------
_BACKEND = Path(__file__).resolve().parents[1]
_RESULTS = _BACKEND / "data" / "classification" / "results"
_ADAPTER = _BACKEND / "data" / "classification" / "experiments" / "lora_task88"
_TEST_SPLIT = _BACKEND / "data" / "classification" / "splits" / "test.jsonl"


def _sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.skipif(
    not (_RESULTS / "baseline_predictions.jsonl").exists(),
    reason="Task 87 baseline artifacts not present",
)
class TestRealArtifactsNoMutation:
    def test_baseline_artifact_ids_match_held_out_test_split(self):
        # Same 12 example IDs and matching gold labels between Task 87 artifacts
        # and the current held-out test split.
        base = ev.load_baseline_predictions(_RESULTS)
        gold = {}
        with _TEST_SPLIT.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rec = json.loads(line)
                    gold[rec["example_id"]] = rec["label"]
        base_ids = {r["example_id"] for r in base}
        assert base_ids == set(gold)
        for r in base:
            assert r["gold_label"] == gold[r["example_id"]]

    def test_baseline_rows_all_invalid_task87(self):
        # Task 87 recorded 0 valid / 12 invalid (invalid_format).
        rows = [ev.normalize_baseline_row(p) for p in ev.load_baseline_predictions(_RESULTS)]
        assert len(rows) == 12
        assert all(not r["is_valid_output"] for r in rows)
        m = ev.compute_comparison_metrics(rows)
        assert m["primary_accuracy"] == 0.0
        assert m["valid_accuracy"] is None

    def test_reading_artifacts_does_not_mutate_them(self):
        # Reading + scoring must not rewrite the frozen Task 87 artifacts.
        before = _sha(_RESULTS / "baseline_predictions.jsonl")
        ev.load_baseline_predictions(_RESULTS)
        after = _sha(_RESULTS / "baseline_predictions.jsonl")
        assert before == after


@pytest.mark.skipif(not _ADAPTER.exists(), reason="Task 88 adapter not present")
class TestTask88AdapterConfig:
    def test_adapter_base_model_is_smollm2_135m(self):
        base = ev.read_adapter_base_model(_ADAPTER)
        assert base == "HuggingFaceTB/SmolLM2-135M"

    def test_held_out_test_split_still_12_examples(self):
        with _TEST_SPLIT.open(encoding="utf-8") as fh:
            n = sum(1 for line in fh if line.strip())
        assert n == 12

        assert len(ev.prompt_fingerprint()) == 64  # sha256 hex
