# Task 88 — LoRA Fine-Tuning (EXECUTED)

**Phase:** 4 complete — real training run, real saved adapter, verified reload + inference.

---

## 1. Status: executed (was blocked; blocker resolved)

The earlier blocker was: (1) no ML packages in any venv, and (2) the planned
`meta-llama/Llama-3.2-1B` is gated (HTTP 401, no local HF checkpoint). Both were
resolved:

1. **ML packages** installed into a NEW isolated venv `backend/.venv-ft`
   (Python 3.12.15) via `backend/data/classification/requirements-ft.txt`.
   Existing `.venv`, `.venv-mcp`, `.venv-voice` were **not** mutated.
2. **Base model** switched to the smallest ungated llama-style causal-LM,
   `HuggingFaceTB/SmolLM2-135M` (~0.27 GB, 135M params, no token, no cost).
   Same projection names → identical LoRA target modules. Recorded in
   `run_metadata.json` and `experiments/lora_task88/EXPERIMENT.md`.

A real run trained on `train` (33), validated on `validation` (11), and never
touched `test` (12). See `experiments/lora_task88/run_metadata.json` for the
measured losses, accuracy, dependency versions, duration, and split roles.

---

## 2. Executed configuration

| Dimension | Value |
|---|---|
| Base model | `HuggingFaceTB/SmolLM2-135M` @ `main` (ungated; replaces gated Llama-3.2-1B) |
| Method | label-masked causal-LM classification (gold label = target only, never in input) |
| LoRA | rank=16, alpha=32, dropout=0.05, targets = `{q,k,v,o,gate,up,down}_proj` |
| LR / weight decay | 2e-4 / 0.0 |
| Batch size (train/eval) | 4 / 4 |
| Grad accum | 2 |
| Epochs | 2 |
| Max seq length | 128 |
| Optimizer | AdamW (`weight_decay`=0.0) |
| Precision | fp32 (CPU; fp16 unsupported on CPU) |
| Eval during training | **off** (final validation pass only, incl. greedy accuracy) |
| Seed | 42 |
| Dataset | `data/classification/splits/{train:33,validation:11,test:12}`, version 1.0 |

**Measured (honest):** train loss [1.6226, 0.7226]; validation loss 0.6133,
accuracy 3/11, 0 invalid. Low accuracy is expected for 135M × 2 epochs × 33
examples — reported as-is, not inflated. Meaningful comparison to Task 87 is
Task 89's job on the untouched held-out test split.

---

## 3. Files created by this experiment

```
backend/data/classification/
├── dataset.py                      # read-only dataset accessors + validation
├── requirements-ft.txt             # pip manifest for the NEW fine-tuning venv
└── experiments/lora_task88/        # task-88 outputs (never touches Task 86/87)
    ├── adapter_model.bin
    ├── adapter_config.json
    ├── training_args.json
    ├── run_metadata.json
    ├── logs/train.log
    └── README.md
```

---

## 4. Isolation guarantees

- The experiment directory stores **only** its own adapter + metadata. Task 86
  (`corpus.jsonl`, `splits/`) and Task 87 (`results/baseline_predictions.jsonl`,
  `results/baseline_report.json`, `results/baseline_report.txt`) are **never read
  or rewritten** by the trainer (train split only used for gradient updates;
  validation split only for the final config-check).
- Base-model weights, the cache, and this document live outside the commit scope.
- The script refuses to run when `torch/transformers/peft` are missing, so a
  half-installed checkout cannot silently produce a stale run.
