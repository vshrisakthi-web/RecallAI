"""Task 88 LoRA trainer for the classification experiment.

Builds a small LoRA adapter on top of a small causal LM and writes it (plus
training args, tokenizer, and run metadata) into an experiment directory.

CLI::

    backend/.venv-ft/bin/python -m app.scripts.train_classification_lora \\
        --config backend/app/scripts/configs/lora_config.py \\
        --out-dir data/classification/experiments/lora_task88

Installation gate::

    # NEW isolated env, python 3.9
    python3.9 -m venv backend/.venv-ft
    backend/.venv-ft/bin/pip install -r backend/data/classification/requirements-ft.txt

Gold-label isolation: this module only *reads* labels (for batch construction and
metrics).  It never embeds a gold label into a prompt or a training batch, so the
predictor backend stays the only consumer of labels.

Note: This module imports torch/transformers/peft inside a guarded block so that
the config/data helpers can be tested before the ML environment is installed.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("lora_task88")

# ---- optional ML imports (guarded so config/data tests can import this module) --
try:  # pragma: no cover - only fails until the approved pip install lands
    import torch  # noqa: F401
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import get_peft_model, LoraConfig as PEFT_LoraConfig

    HAS_TORCH = True
    HAS_TRANSFORMERS = True
    HAS_PEFT = True
except ImportError:  # pragma: no cover
    HAS_TORCH = False
    HAS_TRANSFORMERS = False
    HAS_PEFT = False


def _require_ml() -> None:
    if not (HAS_TORCH and HAS_TRANSFORMERS and HAS_PEFT):
        raise RuntimeError(
            "ML dependencies (torch/ transformers/ peft) are not installed. "
            "Run: backend/.venv-ft/bin/pip install -r backend/data/classification/requirements-ft.txt"
        )


# ---- read-only dataset layer (no torch here) ----------------------------------
from data.classification import dataset as ds  # type: ignore  # noqa: E402

# ---- config layer (no torch here) ----------------------------------------------
from app.scripts.configs.lora_config import LoRAConfig  # type: ignore  # noqa: E402

# Hyperparameters are intentionally small (few hundred lines, CPU-only) so the run
# finishes in minutes and the learning signal is visible on 33 training examples.

# ---- model / tokenizer wiring (heavy imports inside) ---------------------------
def build_model_and_tokenizer(cfg: LoRAConfig) -> Tuple[Any, Any]:
    """Load the HF base model + tokenizer and wrap it with the LoRA adapter."""
    _require_ml()
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import get_peft_model, LoraConfig as PEFT_LoraConfig

    logger.info("Loading base model: %s @ %s", cfg.base_model_id, cfg.base_model_revision)
    tokenizer = AutoTokenizer.from_pretrained(
        cfg.base_model_id, revision=cfg.base_model_revision
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        cfg.base_model_id, revision=cfg.base_model_revision
    )
    lora_cfg = PEFT_LoraConfig(
        r=cfg.rank,
        lora_alpha=cfg.alpha,
        lora_dropout=cfg.dropout,
        target_modules=list(cfg.target_modules),
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_cfg)
    logger.info("LoRA adapter created: %s", lora_cfg)
    return model, tokenizer


# ---- classification prompt (fixed; gold label never appears in the input) -----
# The model input is instruction + text only.  The gold label is used solely as
# the supervised target (see encode_classification), so it never leaks into the
# prompt.  Kept identical to the Task 87 label set for Task 89 comparability.
CLASSIFICATION_PROMPT = (
    "Classify the text as exactly one of BUG, DECISION, TASK, or LEARNING.\n"
    "Text: {text}\nLabel:"
)
CLASSIFY_LABELS = ["BUG", "DECISION", "TASK", "LEARNING"]


def build_classification_text(text: str) -> str:
    """Return the model input for a text (instruction + text, no gold label)."""
    return CLASSIFICATION_PROMPT.format(text=text)


def encode_classification(tokenizer: Any, records: List[dict], max_length: int) -> Any:
    """Tokenize records for label-masked causal-LM classification.

    The input is ``instruction + text`` (NO gold label).  The label is appended
    as the only supervised target: every prompt token gets ``-100`` in the
    ``labels`` tensor so the loss is computed exclusively on the label token(s).
    Prompts are truncated from the left when needed so the label always fits.
    """
    pad_id = tokenizer.pad_token_id
    if pad_id is None:
        pad_id = tokenizer.eos_token_id or 0

    seqs: List[Tuple[List[int], List[int]]] = []
    for rec in records:
        prompt_ids = tokenizer(
            build_classification_text(rec["text"]), add_special_tokens=True
        )["input_ids"]
        label_ids = tokenizer(
            " " + rec["label"], add_special_tokens=False
        )["input_ids"]
        if len(prompt_ids) + len(label_ids) > max_length:
            keep = max(1, max_length - len(label_ids))
            prompt_ids = prompt_ids[-keep:]
        input_ids = list(prompt_ids) + list(label_ids)
        labels = [-100] * len(prompt_ids) + list(label_ids)
        seqs.append((input_ids, labels))

    longest = min(max(len(i) for i, _ in seqs), max_length)
    input_batch: List[List[int]] = []
    label_batch: List[List[int]] = []
    attn_batch: List[List[int]] = []
    for input_ids, labels in seqs:
        input_ids = input_ids[:max_length]
        labels = labels[:max_length]
        pad_len = longest - len(input_ids)
        input_batch.append(input_ids + [pad_id] * pad_len)
        label_batch.append(labels + [-100] * pad_len)
        attn_batch.append([1] * len(input_ids) + [0] * pad_len)

    return {
        "input_ids": torch.tensor(input_batch, dtype=torch.long),
        "attention_mask": torch.tensor(attn_batch, dtype=torch.long),
        "labels": torch.tensor(label_batch, dtype=torch.long),
    }


# Backwards-compatible alias (the label-masked encoder supersedes the old
# full-sequence next-token encoder).
def encode_records(tokenizer: Any, records: List[dict], max_length: int) -> Any:
    """Deprecated: use encode_classification (label-masked) instead."""
    return encode_classification(tokenizer, records, max_length)


def predict_label(
    model: Any,
    tokenizer: Any,
    text: str,
    max_new_tokens: int = 4,
    device: Any = None,
) -> str:
    """Generate a single label for ``text`` and normalize to one of the four.

    Returns one of BUG/DECISION/TASK/LEARNING, or "INVALID" when the generated
    text does not start with a permitted label (honest failure accounting).
    """
    if device is None:
        device = torch.device("cpu")
    prompt = build_classification_text(text)
    inputs = tokenizer(prompt, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}
    pad_id = tokenizer.pad_token_id or tokenizer.eos_token_id
    with torch.no_grad():
        gen = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=pad_id,
        )
    decoded = tokenizer.decode(
        gen[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True
    ).strip().upper()
    for label in CLASSIFY_LABELS:
        if decoded.startswith(label):
            return label
    return "INVALID"


def _run_batch_loss(
    model: Any, batch: Any, attention_mask: Any, device: torch.device
) -> Tuple[Any, int]:
    """Run a single forward pass and return (loss_tensor, num_examples).

    Returns the *tensor* (not a float) so callers can ``backward()`` during
    training; validation callers read ``loss.item()`` under ``no_grad``.
    """
    batch = {k: v.to(device) for k, v in batch.items()}
    outputs = model(**batch)
    loss = outputs.loss
    if loss is None:
        raise RuntimeError(
            "Model returned loss=None. encode_records must set labels=input_ids "
            "so the causal LM computes a next-token loss."
        )
    return loss, int(batch["input_ids"].size(0))


# ---- training loop (manual; no Trainer) ---------------------------------------
def train_one_epoch(
    model: Any,
    tokenizer: Any,
    train_records: List[dict],
    optimizer: Any,
    device: torch.device,
    max_length: int,
    batch_size: int,
    grad_accum: int,
) -> Tuple[float, int]:
    """Run one training epoch and return (mean_loss, num_examples)."""
    model.train()
    optimizer.zero_grad()

    total_loss = 0.0
    total_examples = 0
    batch_chunks = [
        train_records[i : i + batch_size]
        for i in range(0, len(train_records), batch_size)
    ]

    for chunk in batch_chunks:
        enc = encode_classification(tokenizer, chunk, max_length)
        loss, n = _run_batch_loss(model, enc, enc["attention_mask"], device)
        loss_value = loss / grad_accum
        loss_value.backward()
        if n % grad_accum == 0:
            optimizer.step()
            optimizer.zero_grad()
        total_loss += loss.item() * n
        total_examples += n

    # Handle a trailing incomplete accumulation window.
    if total_examples % grad_accum != 0:
        optimizer.step()
        optimizer.zero_grad()

    return (total_loss / total_examples) if total_examples else 0.0, total_examples


# ---- validation + checkpointing (heavy deps inside) ----------------------------
def compute_validation_metrics(
    model: Any,
    tokenizer: Any,
    val_records: List[dict],
    device: torch.device,
    max_length: int,
    batch_size: int,
) -> Dict[str, Any]:
    """Run a single pass over the validation split (no optimizer step)."""
    model.eval()
    total_loss = 0.0
    n_valid = 0
    batch_chunks = [
        val_records[i : i + batch_size]
        for i in range(0, len(val_records), batch_size)
    ]
    with torch.no_grad():
        for chunk in batch_chunks:
            enc = encode_classification(tokenizer, chunk, max_length)
            loss, _ = _run_batch_loss(model, enc, enc["attention_mask"], device)
            total_loss += loss.item() * len(chunk)
            n_valid += len(chunk)

    # Classification accuracy (greedy label generation) — a meaningful signal
    # beyond LM loss.  Uses predict_label so the metric reflects the exact
    # inference path a downstream consumer (Task 89) will use.
    correct = 0
    invalid = 0
    for rec in val_records:
        pred = predict_label(model, tokenizer, rec["text"], device=device)
        if pred == "INVALID":
            invalid += 1
        elif pred == rec["label"]:
            correct += 1
    accuracy = correct / n_valid if n_valid else 0.0
    return {
        "num_examples": n_valid,
        "mean_loss": total_loss / n_valid if n_valid else 0.0,
        "accuracy": accuracy,
        "correct": correct,
        "invalid_predictions": invalid,
    }


def save_checkpoint(out_dir: Path, model: Any, tokenizer: Any, cfg: LoRAConfig, metrics: Dict[str, Any]) -> None:
    """Write adapter weights + tokenizer + adapter/training metadata to out_dir.

    The adapter weight file (``adapter_model.bin``) and the tokenizer files are
    produced by the model/tokenizer ``save_pretrained`` hooks.  The
    ``adapter_config.json`` and ``training_args.json`` snapshots are written here
    so the experiment is reproducible and inspectable without re-loading
    torch/peft — this keeps the on-disk contract deterministic and testable.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out_dir, safe_serialization=False)
    tokenizer.save_pretrained(out_dir)

    snapshot = cfg.to_dict()
    metadata_snapshot = {
        "base_model_id": snapshot["base_model_id"],
        "base_model_revision": snapshot["base_model_revision"],
        "lora": snapshot["lora"],
    }
    # Preserve PEFT's own reloadable adapter_config.json when a real model wrote
    # it (it contains peft_type/target_modules required by PeftModel.from_pretrained).
    # Only author our documented snapshot when save_pretrained did not produce one
    # (e.g. the deterministic _FakeModel in unit tests).
    adapter_config_path = out_dir / "adapter_config.json"
    if not adapter_config_path.exists():
        adapter_config_path.write_text(
            json.dumps(metadata_snapshot, indent=2), encoding="utf-8"
        )
    # Always record our human-readable snapshot under a distinct name so the
    # documented base-model/LoRA metadata is never clobbered by PEFT.
    (out_dir / "adapter_metadata.json").write_text(
        json.dumps(metadata_snapshot, indent=2), encoding="utf-8"
    )
    (out_dir / "training_args.json").write_text(
        json.dumps(snapshot["training"], indent=2), encoding="utf-8"
    )



def run_pipeline(cfg: LoRAConfig, out_dir: Path, train_records: List[dict], val_records: List[dict]) -> Dict[str, Any]:
    """Train -> validate -> save; returns run metadata (JSON-serializable).

    Real entry path: refuses to run when torch/transformers/peft are missing
    (``_require_ml``).  The transformers + peft imports live inside
    ``build_model_and_tokenizer`` so torch-free tests can target the
    torch-free helpers in isolation.
    """
    _require_ml()
    from transformers import AutoModelForCausalLM, AutoTokenizer

    _started_at = time.monotonic()
    device = torch.device("cpu")
    model, tokenizer = build_model_and_tokenizer(cfg)
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg.lr)

    epoch_losses: List[float] = []
    for epoch in range(cfg.epochs):
        epoch_loss, _ = train_one_epoch(
            model,
            tokenizer,
            train_records,
            optimizer,
            device,
            cfg.max_seq_length,
            cfg.train_batch_size,
            cfg.grad_accum,
        )
        epoch_losses.append(epoch_loss)
        logger.info("Epoch %d done: train loss %.6f", epoch + 1, epoch_loss)

    metrics = compute_validation_metrics(
        model, tokenizer, val_records, device, cfg.max_seq_length, cfg.eval_batch_size
    )
    logger.info("Final validation pass: %s", metrics)

    save_checkpoint(out_dir, model, tokenizer, cfg, metrics)
    duration_seconds = time.monotonic() - _started_at
    logger.info("Training finished in %.1fs", duration_seconds)
    metadata = _build_metadata(
        cfg,
        out_dir,
        train_records,
        val_records,
        metrics,
        HAS_TORCH and HAS_TRANSFORMERS and HAS_PEFT,
        duration_seconds=duration_seconds,
        epoch_losses=list(epoch_losses),
    )
    (out_dir / "run_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return metadata


def _build_metadata(
    cfg: LoRAConfig,
    out_dir: Path,
    train_records: List[dict],
    val_records: List[dict],
    metrics: Dict[str, Any],
    ml_available: bool,
    duration_seconds: Optional[float] = None,
    epoch_losses: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """Assemble the JSON-serializable run metadata (no heavy imports here)."""
    metadata: Dict[str, Any] = {
        "dataset_version": ds.DATASET_VERSION,
        "base_model_id": cfg.base_model_id,
        "base_model_revision": cfg.base_model_revision,
        "lora_config": cfg.to_dict(),
        "environment": {"ml_available": ml_available, **_dependency_versions()},
        "train_size": len(train_records),
        "val_size": len(val_records),
        "metrics": metrics,
        "output_dir": str(out_dir),
        # Split-role safety: this run trains on train + validates on validation;
        # the held-out test split is never loaded here.
        "split_roles": {
            "trained_on": "train",
            "validated_on": "validation",
            "held_out_and_not_used": "test",
        },
        "evaluation_timestamp": datetime.now(timezone.utc).isoformat(),
        "reproduce_command": (
            f"backend/.venv-ft/bin/python -m app.scripts.train_classification_lora "
            f"--config backend/app/scripts/configs/lora_config.py "
            f"--train-split train --val-split validation "
            f"--out-dir {out_dir}"
        ),
    }
    if duration_seconds is not None:
        metadata["training_duration_seconds"] = round(duration_seconds, 2)
    if epoch_losses:
        metadata["train_loss_per_epoch"] = [round(x, 6) for x in epoch_losses]
    return metadata


def _dependency_versions() -> Dict[str, str]:
    """Best-effort installed versions of the ML stack (empty when unavailable)."""
    versions: Dict[str, str] = {}
    for pkg in ("torch", "transformers", "peft", "accelerate", "tokenizers", "numpy"):
        try:
            versions[pkg] = importlib_metadata.version(pkg)
        except Exception:  # noqa: BLE001 - package simply not installed
            continue
    return versions


# ---- CLI ---------------------------------------------------------------------
def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Task 88 LoRA fine-tuning (CPU-only).")
    parser.add_argument("--config", type=Path, required=True, help="Path to a LoRAConfig (YAML or JSON).")
    parser.add_argument("--train-split", default="train", help="Split to train on (default: train).")
    parser.add_argument("--val-split", default="validation", help="Split to validate on (default: validation).")
    parser.add_argument("--out-dir", type=Path, required=True, help="Experiment output directory.")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point: load config + splits, train, save metadata, log summary."""
    args = parse_args(argv)

    if args.config is not None:
        with args.config.open(encoding="utf-8") as fh:
            cfg = LoRAConfig.from_dict(json.load(fh))
    else:
        cfg = _default_config()

    out_dir = args.out_dir
    if not out_dir.is_absolute():
        out_dir = Path.cwd() / out_dir

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.info("LoRA config: %s", cfg.to_dict())

    train_records = ds.load_split(args.train_split)
    val_records = ds.load_split(args.val_split)
    logger.info("Splits loaded: train=%d val=%d", len(train_records), len(val_records))

    metadata = run_pipeline(cfg, out_dir, train_records, val_records)
    logger.info("Run complete. Metadata: %s", json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


