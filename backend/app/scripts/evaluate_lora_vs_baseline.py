"""Task 89: compare the Task 87 prompt-only baseline with the Task 88 LoRA
fine-tuned classifier on the same 12 held-out test examples.

Read-only w.r.t. prior work:
  * Task 87 predictions are loaded from the frozen ``baseline_predictions.jsonl``
    (never regenerated).
  * Task 88 adapter is loaded from ``experiments/lora_task88`` (never retrained).

Heavy ML imports (torch/transformers/peft) are performed lazily inside
``load_lora_model`` so the metric/report helpers can be imported and unit-tested
without an ML environment.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.services.classification import (
    ALLOWED_LABELS,
    DATASET_VERSION,
    PROMPT_VERSION,
    prompt_fingerprint,
)
from data.classification import dataset as ds  # type: ignore  # noqa: E402
from app.scripts import train_classification_lora as trainer  # type: ignore  # noqa: E402

LABEL_ORDER = list(ALLOWED_LABELS)  # fixed: BUG, DECISION, TASK, LEARNING

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_RESULTS_DIR = _BACKEND_DIR / "data" / "classification" / "results"
_ADAPTER_DIR = _BACKEND_DIR / "data" / "classification" / "experiments" / "lora_task88"
_OUT_DIR = _RESULTS_DIR / "task89_comparison"


# ---------------------------------------------------------------------------
# Metric policy (single documented policy used for BOTH systems)
# ---------------------------------------------------------------------------
#  * PRIMARY accuracy  = correct / total_examples   (invalid/failed counted wrong)
#  * SECONDARY accuracy = correct / valid_predictions (reported only, never primary)
#  * Macro P/R/F1 = unweighted mean over the four fixed classes.
#  * Zero-division: a class with no predicted (P) or no gold (R) support scores 0.0.
#  * Confusion matrix counts only VALID predictions; invalid/failed rows are
#    tracked separately in ``error_categories`` and the valid/invalid counts.
def compute_comparison_metrics(
    predictions: List[Dict[str, Any]],
    label_order: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Compute the documented Task 89 metric policy for one system.

    Each item in ``predictions`` must carry: ``example_id``, ``gold_label``,
    ``predicted_label``, ``is_valid_output`` (bool), ``error_category`` (optional),
    ``inference_latency_ms`` (number).
    """
    label_order = list(label_order or LABEL_ORDER)
    label_set = set(label_order)

    total = len(predictions)
    valid_preds = [p for p in predictions if p.get("is_valid_output")]
    valid_count = len(valid_preds)
    invalid_count = total - valid_count

    correct = sum(
        1 for p in valid_preds if p.get("predicted_label") == p.get("gold_label")
    )
    primary_accuracy = (correct / total) if total else 0.0
    valid_accuracy = (correct / valid_count) if valid_count else None

    confusion: Dict[str, Dict[str, int]] = {
        g: {p: 0 for p in label_order} for g in label_order
    }
    error_categories: Counter = Counter()
    latencies: List[float] = []
    for p in predictions:
        latencies.append(float(p.get("inference_latency_ms") or 0.0))
        if not p.get("is_valid_output"):
            cat = p.get("error_category")
            if cat:
                error_categories[cat] += 1
            continue
        g = p.get("gold_label")
        pr = p.get("predicted_label")
        if g in confusion and pr in confusion[g]:
            confusion[g][pr] += 1

    precision: Dict[str, float] = {}
    recall: Dict[str, float] = {}
    f1: Dict[str, float] = {}
    for label in label_order:
        tp = confusion[label][label]
        fp = sum(confusion[g][label] for g in label_order if g != label)
        fn = sum(confusion[label][pp] for pp in label_order if pp != label)
        precision[label] = tp / (tp + fp) if (tp + fp) else 0.0
        recall[label] = tp / (tp + fn) if (tp + fn) else 0.0
        prec_rec = precision[label] + recall[label]
        f1[label] = (2 * precision[label] * recall[label] / prec_rec) if prec_rec else 0.0

    macro_precision = sum(precision.values()) / len(label_order)
    macro_recall = sum(recall.values()) / len(label_order)
    macro_f1 = sum(f1.values()) / len(label_order)

    support = Counter(
        p["gold_label"] for p in predictions if p.get("gold_label") in label_set
    )

    sorted_lat = sorted(latencies) if latencies else [0.0]
    n = len(sorted_lat)
    median = sorted_lat[n // 2] if n % 2 else (sorted_lat[n // 2 - 1] + sorted_lat[n // 2]) / 2
    mean = sum(latencies) / len(latencies) if latencies else 0.0

    return {
        "total": total,
        "valid": valid_count,
        "invalid": invalid_count,
        "valid_output_rate": round((valid_count / total) if total else 0.0, 4),
        "correct": correct,
        # Primary metric: invalid/failed predictions counted as incorrect.
        "primary_accuracy": round(primary_accuracy, 4),
        # Secondary metric: among valid predictions only (None when no valid).
        "valid_accuracy": (round(valid_accuracy, 4) if valid_accuracy is not None else None),
        "macro_precision": round(macro_precision, 4),
        "macro_recall": round(macro_recall, 4),
        "macro_f1": round(macro_f1, 4),
        "precision": {l: round(precision[l], 4) for l in label_order},
        "recall": {l: round(recall[l], 4) for l in label_order},
        "f1": {l: round(f1[l], 4) for l in label_order},
        "support": {l: support.get(l, 0) for l in label_order},
        "confusion_matrix": confusion,
        "latency_mean_ms": round(mean, 2),
        "latency_median_ms": round(median, 2),
        "error_categories": dict(error_categories),
    }



# ---------------------------------------------------------------------------
# Loading inputs
# ---------------------------------------------------------------------------
def load_baseline_predictions(results_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load the frozen Task 87 predictions from baseline_predictions.jsonl."""
    path = (results_dir or _RESULTS_DIR) / "baseline_predictions.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"Task 87 baseline predictions not found: {path}")
    rows: List[Dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def normalize_baseline_row(pred: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a Task 87 ClassificationPrediction dict to an internal metric row."""
    return {
        "example_id": pred["example_id"],
        "gold_label": pred["gold_label"],
        "predicted_label": pred.get("predicted_label", ""),
        "is_valid_output": bool(pred.get("is_valid_output")),
        "error_category": pred.get("error_category"),
        "inference_latency_ms": float(pred.get("inference_latency_ms") or 0.0),
    }


def read_adapter_base_model(adapter_dir: Optional[Path] = None) -> str:
    """Read the base-model id the Task 88 adapter was trained on."""
    cfg_path = (adapter_dir or _ADAPTER_DIR) / "adapter_config.json"
    if not cfg_path.exists():
        raise FileNotFoundError(f"adapter_config.json not found: {cfg_path}")
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    base = data.get("base_model_name_or_path")
    if not base:
        raise ValueError("adapter_config.json missing 'base_model_name_or_path'")
    return base


def load_lora_model(
    adapter_dir: Optional[Path] = None, base_model_id: Optional[str] = None
) -> Tuple[Any, Any]:
    """Load the SAVED Task 88 adapter (never retrained).

    Lazy heavy imports so the module can be imported without an ML env.
    """
    adapter_dir = adapter_dir or _ADAPTER_DIR
    base_model_id = base_model_id or read_adapter_base_model(adapter_dir)
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    tokenizer = AutoTokenizer.from_pretrained(str(adapter_dir))
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    base = AutoModelForCausalLM.from_pretrained(base_model_id)
    model = PeftModel.from_pretrained(base, str(adapter_dir))
    model.eval()
    return model, tokenizer


def run_lora_predictions(
    model: Any, tokenizer: Any, test_records: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Run the saved adapter on test texts (gold label never in the input)."""
    import time

    rows: List[Dict[str, Any]] = []
    for rec in test_records:
        text = rec["text"]
        t0 = time.perf_counter()
        label = trainer.predict_label(model, tokenizer, text)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        valid = label in trainer.CLASSIFY_LABELS
        rows.append(
            {
                "example_id": rec["example_id"],
                "gold_label": rec["label"],
                "predicted_label": label if valid else "",
                "is_valid_output": valid,
                "error_category": None if valid else "invalid_format",
                "inference_latency_ms": round(latency_ms, 2),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------
def _index_by_id(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {r["example_id"]: r for r in rows}


def build_comparison(
    baseline_rows: List[Dict[str, Any]],
    lora_rows: List[Dict[str, Any]],
    test_records: List[Dict[str, Any]],
    prompt_fp: str,
    base_model_id: str,
    adapter_dir: Path,
    run_metadata: Optional[Dict[str, Any]],
    timestamp: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Build the per-example comparison rows and the full report dict."""
    gold_by_id = {r["example_id"]: r["label"] for r in test_records}
    example_ids = [r["example_id"] for r in sorted(test_records, key=lambda x: x["example_id"])]

    base_by_id = _index_by_id(baseline_rows)
    lora_by_id = _index_by_id(lora_rows)

    combined: List[Dict[str, Any]] = []
    for ex_id in example_ids:
        b = base_by_id.get(ex_id, {})
        l = lora_by_id.get(ex_id, {})
        combined.append(
            {
                "dataset_version": DATASET_VERSION,
                "split_name": "test",
                "example_id": ex_id,
                "gold_label": gold_by_id.get(ex_id, ""),
                "task87": {
                    "model_id": "llama3.2:1b@ollama(prompt-only)",
                    "predicted_label": b.get("predicted_label", ""),
                    "is_valid_output": bool(b.get("is_valid_output")),
                    "error_category": b.get("error_category"),
                    "inference_latency_ms": float(b.get("inference_latency_ms") or 0.0),
                    "prompt_version": PROMPT_VERSION,
                    "prompt_fingerprint": prompt_fp,
                },
                "task88": {
                    "model_id": f"{base_model_id}+LoRA(adapter)",
                    "predicted_label": l.get("predicted_label", ""),
                    "is_valid_output": bool(l.get("is_valid_output")),
                    "error_category": l.get("error_category"),
                    "inference_latency_ms": float(l.get("inference_latency_ms") or 0.0),
                    "adapter_path": str(adapter_dir),
                    "base_model_id": base_model_id,
                },
                "evaluation_timestamp": timestamp,
            }
        )

    baseline_metrics = compute_comparison_metrics(baseline_rows)
    lora_metrics = compute_comparison_metrics(lora_rows)

    missing_in_baseline = [i for i in example_ids if i not in base_by_id]
    missing_in_lora = [i for i in example_ids if i not in lora_by_id]


    report: Dict[str, Any] = {
        "objective": (
            "Compare the Task 87 prompt-only baseline with the Task 88 LoRA "
            "fine-tuned classifier on the identical 12 held-out test examples "
            "using one documented metric policy."
        ),
        "methodology": (
            "Task 87 predictions are loaded unchanged from the frozen "
            "baseline_predictions.jsonl. Task 88 adapter is reloaded with "
            "PeftModel.from_pretrained (never retrained) and run once on the test "
            "texts. Gold labels are kept separate from model input and used only "
            "for scoring. One metric policy is applied to both: primary accuracy = "
            "correct/total (invalid counted wrong); secondary accuracy = "
            "correct/valid; macro P/R/F1 = unweighted mean over the four fixed "
            "classes with zero-valued zero-division cases."
        ),
        "metric_policy": {
            "label_order": LABEL_ORDER,
            "primary_accuracy_definition": "correct / total_examples (invalid/failed counted incorrect)",
            "valid_accuracy_definition": "correct / valid_predictions (secondary, reported only)",
            "macro_definition": "unweighted mean of per-class scores over the four fixed classes",
            "zero_division": "0.0 when a class has no predicted (P) or no gold (R) support",
            "confusion_matrix": "counts valid predictions only; invalid rows tracked separately",
        },
        "dataset_version": DATASET_VERSION,
        "split_name": "test",
        "label_order": LABEL_ORDER,
        "example_ids": example_ids,
        "input_alignment": {
            "baseline_covers_all_example_ids": not missing_in_baseline,
            "lora_covers_all_example_ids": not missing_in_lora,
            "missing_in_baseline": missing_in_baseline,
            "missing_in_lora": missing_in_lora,
        },
        "task87_baseline": {
            "description": "Prompt-only llama3.2:1b via local Ollama (frozen prompt).",
            "prompt_version": PROMPT_VERSION,
            "prompt_fingerprint": prompt_fp,
            "model_id": "llama3.2:1b@ollama(prompt-only)",
            "metrics": baseline_metrics,
        },
        "task88_finetuned": {
            "description": "LoRA fine-tuned classifier (base model + saved adapter).",
            "base_model_id": base_model_id,
            "adapter_path": str(adapter_dir),
            "run_metadata": run_metadata or {},
            "metrics": lora_metrics,
        },
        "side_by_side": {
            "primary_accuracy": {
                "task87": baseline_metrics["primary_accuracy"],
                "task88": lora_metrics["primary_accuracy"],
            },
            "valid_output_rate": {
                "task87": baseline_metrics["valid_output_rate"],
                "task88": lora_metrics["valid_output_rate"],
            },
            "macro_f1": {
                "task87": baseline_metrics["macro_f1"],
                "task88": lora_metrics["macro_f1"],
            },
            "valid_accuracy": {
                "task87": baseline_metrics["valid_accuracy"],
                "task88": lora_metrics["valid_accuracy"],
            },
        },
        "confusion_matrices": {
            "label_order": LABEL_ORDER,
            "task87": baseline_metrics["confusion_matrix"],
            "task88": lora_metrics["confusion_matrix"],
        },
        "per_class": {
            "task87": {
                "precision": baseline_metrics["precision"],
                "recall": baseline_metrics["recall"],
                "f1": baseline_metrics["f1"],
                "support": baseline_metrics["support"],
            },
            "task88": {
                "precision": lora_metrics["precision"],
                "recall": lora_metrics["recall"],
                "f1": lora_metrics["f1"],
                "support": lora_metrics["support"],
            },
        },
        "latency": {
            "task87": {
                "mean_ms": baseline_metrics["latency_mean_ms"],
                "median_ms": baseline_metrics["latency_median_ms"],
            },
            "task88": {
                "mean_ms": lora_metrics["latency_mean_ms"],
                "median_ms": lora_metrics["latency_median_ms"],
            },
        },
        "inference_config": {
            "task87": {
                "backend": "ollama",
                "model": "llama3.2:1b",
                "note": "temperature 0, num_predict 8 (as recorded in Task 87 run).",
            },
            "task88": {
                "backend": "peft/adapter (CPU)",
                "decoding": "greedy (do_sample=False), max_new_tokens=4",
                "base_model_id": base_model_id,
            },
        },
        "reproducibility": {
            "dataset_version": DATASET_VERSION,
            "prompt_version": PROMPT_VERSION,
            "prompt_fingerprint": prompt_fp,
            "adapter_path": str(adapter_dir),
            "run_timestamp": timestamp,
            "commands": [
                "cd backend && .venv-ft/bin/python -m app.scripts.evaluate_lora_vs_baseline",
            ],
        },
        "limitations": [
            "This compares two complete SYSTEMS with different base models "
            "(prompt-only llama3.2:1b vs LoRA fine-tuned SmolLM2-135M); it is NOT "
            "the isolated causal effect of fine-tuning on a shared base model.",
            "The held-out test set has only 12 examples and only ONE TASK example, "
            "so all per-class results (especially TASK) are highly uncertain.",
            "Task 87 returned 0 valid predictions. A model producing valid labels "
            "improves operational usability, but valid formatting alone does not "
            "prove classification correctness.",
            "Both models were frozen before this evaluation; no configuration was "
            "changed after inspecting test results.",
        ],
        "task90_recommendation": (
            "Proceed to Task 90 only with clearly versioned follow-ups: (1) measure "
            "the same fine-tuning on the llama3.2 base used by Task 87 for a "
            "controlled causal comparison, (2) increase the synthetic corpus (esp. "
            "TASK examples) before drawing per-class conclusions, and (3) fix the "
            "prompt-only baseline's output contract (or raise num_predict) so it can "
            "produce valid labels for a fair formatting-controlled comparison. Treat "
            "all n=12 per-class metrics as directional only."
        ),
        "evaluation_timestamp": timestamp,
    }
    return combined, report


def format_report_text(report: Dict[str, Any]) -> str:
    """Render a concise human-readable text report."""
    L: List[str] = []
    L.append("Task 89 - Prompt-Only Baseline vs LoRA Fine-Tuned Classifier")
    L.append("=" * 64)
    L.append(f"Dataset version : {report['dataset_version']}   Split: {report['split_name']}")
    L.append(f"Example IDs     : {', '.join(report['example_ids'])}")
    L.append(f"Run timestamp   : {report['evaluation_timestamp']}")
    L.append("")
    L.append(f"Objective: {report['objective']}")
    L.append("")
    L.append(f"Metric policy (label order: {', '.join(report['label_order'])})")
    L.append(f"  primary accuracy = {report['metric_policy']['primary_accuracy_definition']}")
    L.append(f"  valid  accuracy = {report['metric_policy']['valid_accuracy_definition']} (secondary)")
    L.append(f"  macro            = {report['metric_policy']['macro_definition']}")
    L.append("")

    def block(title: str, m: Dict[str, Any], model_id: str) -> None:
        L.append(f"{title}  [{model_id}]")
        L.append("-" * 64)
        L.append(
            f"  total={m['total']}  valid={m['valid']}  invalid={m['invalid']}  "
            f"valid_rate={m['valid_output_rate']}"
        )
        L.append(f"  PRIMARY accuracy (correct/total) = {m['primary_accuracy']}")
        va = m["valid_accuracy"]
        L.append(f"  valid accuracy (correct/valid)   = {va if va is not None else 'n/a (no valid)'}")
        L.append(
            f"  macro precision={m['macro_precision']}  recall={m['macro_recall']}  F1={m['macro_f1']}"
        )
        L.append("  per-class (P / R / F1 / support):")
        for lab in report["label_order"]:
            L.append(
                f"    {lab:<9} {m['precision'][lab]:.3f} / {m['recall'][lab]:.3f} / "
                f"{m['f1'][lab]:.3f} / {m['support'][lab]}"
            )
        L.append("  confusion matrix (rows=gold, cols=pred, order BUG,DECISION,TASK,LEARNING):")
        cm = m["confusion_matrix"]
        L.append("           " + " ".join(f"{c[:4]:>5}" for c in report["label_order"]))
        for g in report["label_order"]:
            L.append(f"    {g:<8} " + " ".join(f"{cm[g][p]:>5}" for p in report["label_order"]))
        L.append(f"  latency mean={m['latency_mean_ms']}ms  median={m['latency_median_ms']}ms")
        L.append(f"  error_categories={m['error_categories']}")
        L.append("")

    bm = report["task87_baseline"]["metrics"]
    lm = report["task88_finetuned"]["metrics"]
    block("Task 87 baseline (prompt-only)", bm, report["task87_baseline"]["model_id"])
    block("Task 88 fine-tuned (LoRA)", lm, report["task88_finetuned"]["base_model_id"])

    L.append("Limitations")
    L.append("-" * 64)
    for lim in report["limitations"]:
        L.append(f"  - {lim}")
    L.append("")
    L.append("Task 90 recommendation")
    L.append("-" * 64)
    L.append(f"  {report['task90_recommendation']}")
    L.append("")
    return "\n".join(L)


def main(argv: Optional[List[str]] = None) -> int:
    timestamp = datetime.now(timezone.utc).isoformat()
    prompt_fp = prompt_fingerprint()

    # 1) Frozen Task 87 predictions (read-only).
    baseline_raw = load_baseline_predictions(_RESULTS_DIR)
    baseline_rows = [normalize_baseline_row(p) for p in baseline_raw]

    # 2) Held-out test records (gold labels, kept for scoring only).
    test_records = ds.load_split("test")

    # 3) Reload the saved Task 88 adapter and run it live on the test texts.
    base_model_id = read_adapter_base_model(_ADAPTER_DIR)
    print(f"[task89] reloading adapter from {_ADAPTER_DIR} (base={base_model_id})")
    model, tokenizer = load_lora_model(_ADAPTER_DIR, base_model_id)
    print(f"[task89] running adapter on {len(test_records)} held-out test examples ...")
    lora_rows = run_lora_predictions(model, tokenizer, test_records)

    # 4) Assemble comparison + report.
    run_meta_path = _ADAPTER_DIR / "run_metadata.json"
    run_metadata = (
        json.loads(run_meta_path.read_text(encoding="utf-8")) if run_meta_path.exists() else None
    )
    combined, report = build_comparison(
        baseline_rows,
        lora_rows,
        test_records,
        prompt_fp,
        base_model_id,
        _ADAPTER_DIR,
        run_metadata,
        timestamp,
    )

    # 5) Write artifacts.
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    with (_OUT_DIR / "task89_predictions.jsonl").open("w", encoding="utf-8") as fh:
        for row in combined:
            fh.write(json.dumps(row) + "\n")
    (_OUT_DIR / "task89_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (_OUT_DIR / "task89_report.txt").write_text(format_report_text(report), encoding="utf-8")

    print(format_report_text(report))
    print(f"[task89] artifacts written to {_OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


