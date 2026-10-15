"""LoRA adapter configuration for the Task 88 classification fine-tuning run.

Pure-Python dataclass.  It does not import torch, transformers, peft, or
datasets, so the config can be parsed and validated before the approved ML
environment is installed.

Values deliberately mirror the task spec in
backend/doc/tasks/88_LORA_FINETUNING.md and the approval note (rank=16,
alpha=32, ...) plus the hyperparameter block (lr, batch size, ...).

Only the ML-backend wiring belongs in
backend/app/scripts/train_classification_lora.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# Canonical label list (same order as app.services.classification.ALLOWED_LABELS).
ALLOWED_LABELS = ["BUG", "DECISION", "TASK", "LEARNING"]

# Base model: smallest ungated HF causal-LM with llama-style attention projections.
# The originally planned meta-llama/Llama-3.2-1B is gated (HTTP 401 without a
# token), so Task 88 uses HuggingFaceTB/SmolLM2-135M (~0.27 GB fp16, 135M
# params) which downloads without credentials and trains quickly on CPU.
# It uses the same projection names as llama, so the LoRA target_modules below
# resolve identically.  Recorded in 88_LORA_FINETUNING.md.
BASE_MODEL_ID = "HuggingFaceTB/SmolLM2-135M"
BASE_MODEL_REVISION = "main"

# ---- LoRA hyperparameters (per the task spec) ----
LORA_RANK = 16
LORA_ALPHA = 32
LORA_DROPOUT = 0.05
LORA_TARGET_MODULES = [
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
]

# ---- training hyperparameters ----
INITIAL_LR = 2e-4
WEIGHT_DECAY = 0.0
TRAIN_BATCH_SIZE = 4
EVAL_BATCH_SIZE = 4
GRAD_ACCUM = 2
EPOCHS = 2
MAX_SEQ_LENGTH = 128
SEED = 42


@dataclass(frozen=True)
class LoRAConfig:
    base_model_id: str = BASE_MODEL_ID
    base_model_revision: str = BASE_MODEL_REVISION
    rank: int = LORA_RANK
    alpha: int = LORA_ALPHA
    dropout: float = LORA_DROPOUT
    target_modules: Tuple[str, ...] = field(default_factory=lambda: tuple(LORA_TARGET_MODULES))
    lr: float = INITIAL_LR
    weight_decay: float = WEIGHT_DECAY
    train_batch_size: int = TRAIN_BATCH_SIZE
    eval_batch_size: int = EVAL_BATCH_SIZE
    grad_accum: int = GRAD_ACCUM
    epochs: int = EPOCHS
    max_seq_length: int = MAX_SEQ_LENGTH
    seed: int = SEED
    # CPU training: fp16 is unsupported on CPU, so default to float32.
    fp16: bool = False
    bf16: bool = False
    optimizer: str = "adamw"
    evaluate_during_training: bool = False

    def to_dict(self) -> Dict[str, object]:
        """Serializable snapshot for the run metadata files."""
        return {
            "base_model_id": self.base_model_id,
            "base_model_revision": self.base_model_revision,
            "lora": {
                "rank": self.rank,
                "alpha": self.alpha,
                "dropout": self.dropout,
                "target_modules": list(self.target_modules),
            },
            "training": {
                "learning_rate": self.lr,
                "weight_decay": self.weight_decay,
                "train_batch_size": self.train_batch_size,
                "eval_batch_size": self.eval_batch_size,
                "gradient_accumulation_steps": self.grad_accum,
                "epochs": self.epochs,
                "max_seq_length": self.max_seq_length,
                "seed": self.seed,
                "fp16": self.fp16,
                "bf16": self.bf16,
                "optimizer": self.optimizer,
                "evaluate_during_training": self.evaluate_during_training,
            },
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "LoRAConfig":
        """Construct from a run_metadata_snapshot dict (round-trips to_dict)."""
        lora = payload.get("lora", {})
        training = payload.get("training", {})
        return cls(
            base_model_id=str(payload.get("base_model_id", BASE_MODEL_ID)),
            base_model_revision=str(payload.get("base_model_revision", BASE_MODEL_REVISION)),
            rank=int(lora.get("rank", LORA_RANK)),
            alpha=int(lora.get("alpha", LORA_ALPHA)),
            dropout=float(lora.get("dropout", LORA_DROPOUT)),
            target_modules=tuple(str(m) for m in lora.get("target_modules", LORA_TARGET_MODULES)),
            lr=float(training.get("learning_rate", INITIAL_LR)),
            weight_decay=float(training.get("weight_decay", WEIGHT_DECAY)),
            train_batch_size=int(training.get("train_batch_size", TRAIN_BATCH_SIZE)),
            eval_batch_size=int(training.get("eval_batch_size", EVAL_BATCH_SIZE)),
            grad_accum=int(training.get("gradient_accumulation_steps", GRAD_ACCUM)),
            epochs=int(training.get("epochs", EPOCHS)),
            max_seq_length=int(training.get("max_seq_length", MAX_SEQ_LENGTH)),
            seed=int(training.get("seed", SEED)),
            fp16=bool(training.get("fp16", False)),
            bf16=bool(training.get("bf16", False)),
            optimizer=str(training.get("optimizer", "adamw")),
            evaluate_during_training=bool(training.get("evaluate_during_training", False)),
        )

    def validate(self) -> List[str]:
        """Return a list of human-readable errors (empty when valid)."""
        errors: List[str] = []
        if self.rank < 1 or self.rank > 64:
            errors.append(f"rank {self.rank} outside [1, 64]")
        if self.alpha < 1 or self.alpha <= self.rank:
            errors.append(f"alpha {self.alpha} must be > rank > 0")
        if not (0.0 <= self.dropout < 1.0):
            errors.append(f"dropout {self.dropout} outside [0, 1)")
        if self.train_batch_size % self.grad_accum != 0:
            errors.append(
                f"train_batch_size {self.train_batch_size} not divisible by grad_accum {self.grad_accum}"
            )
        if not self.target_modules:
            errors.append("target_modules must not be empty")
        return errors

    def resolve_base_model(self) -> str:
        """Return the concrete HF base-model id this config trains against."""
        mapping = {BASE_MODEL_ID: "HuggingFaceTB/SmolLM2-135M"}
        return mapping.get(self.base_model_id, self.base_model_id)


def _default_config() -> LoRAConfig:
    return LoRAConfig()


def main() -> None:
    cfg = _default_config()
    print("LoRA config defaults:")
    print(" ", cfg.to_dict())


if __name__ == "__main__":
    main()
