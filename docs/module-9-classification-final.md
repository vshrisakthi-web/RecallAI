# Module 9 – Text Classification Experiment (Tasks 81–90) — Final Report

## 1. Overview

Module 9 added a **four-label text-classification experiment** to RecallAI:

- `BUG` — a defect, failure, unexpected behavior, or reproducible problem.
- `DECISION` — a choice made, direction selected, or explicit agreement.
- `TASK` — an action, deliverable, or follow-up to complete.
- `LEARNING` — knowledge, insight, lesson, or technical concept worth retaining.

The experiment compared two complete classification **systems** on the same held-out
test set and concluded with an explicit **production-integration decision** (Task 90).

> **Headline result: NO classifier is integrated into production.** Neither the
> prompt-only baseline nor the LoRA fine-tuned model met a defensible readiness
> bar on the available evidence. See §7.

## 2. Status of Tasks 81–90

| Task | Area | Status | Evidence source |
|---|---|---|---|
| 81–85 | Dataset authoring, labeling rules, validator, split generation | Complete (prior) | `backend/data/classification/` |
| 86 | Synthetic corpus + train/val/test splits (v1.0, seed 42) | Complete | `corpus.jsonl`, `splits/*.jsonl` |
| 87 | Prompt-only baseline (`llama3.2:1b` via Ollama) | Complete | `results/baseline_*` |
| 88 | PEFT/LoRA fine-tuning (`SmolLM2-135M`) | Complete | `experiments/lora_task88/` |
| 89 | Baseline vs LoRA comparison on held-out test set | Complete | `results/task89_comparison/` |
| 90 | Integration decision, regression tests, documentation | **Complete (this doc)** | §7, §9 |

## 3. Architecture & responsibilities

```
data/classification/
  corpus.jsonl                 # 56 labeled examples (Task 86, immutable)
  splits/{train,validation,test}.jsonl   # 33 / 11 / 12, seed 42, immutable
  validator.py                 # label/schema validation
  splits.py                    # deterministic split generation (seed 42)
  prompts/CLASS_PROMPT_v20241014_01.txt  # frozen prompt (Task 87)
  dataset.py                   # deterministic loader used by Task 88
  results/                     # Task 87 baseline artifacts
  results/task89_comparison/   # Task 89 comparison artifacts
  experiments/lora_task88/     # Task 88 adapter + metadata

app/services/classification.py # prompt-only baseline: prompt, parse, OllamaBackend,
                               #   metric computation, output-contract fix (Task 90)
app/scripts/run_classification_baseline.py   # Task 87 frozen runner
app/scripts/train_classification_lora.py     # Task 88 training + predict_label
app/scripts/configs/lora_config.py           # Task 88 LoRA config
app/scripts/evaluate_lora_vs_baseline.py     # Task 89 evaluator
```

Separation of duties (no leakage): the **gold label** is never sent to any model
input. Task 88 trains on `train.jsonl` only and uses `validation.jsonl` for
validation; the 12 `test.jsonl` examples were reserved until Task 89.

## 4. Dataset & splits (Task 86 — unchanged)

- **Version:** `1.0`, **split seed:** `42`, **total:** 56 examples.
- **Train:** 33 (BUG 7, DECISION 9, LEARNING 7, TASK 10)
- **Validation:** 11 (BUG 3, DECISION 2, LEARNING 3, TASK 1)
- **Test (held-out):** 12 (BUG 4, DECISION 3, LEARNING 4, **TASK 1**)

Example IDs in the held-out test set: `bug_002, bug_007, bug_008, bug_009,
decision_003, decision_004, decision_006, learning_005, learning_008,
learning_012, learning_013, task_011`.

## 5. Measured results (verified against saved artifacts)

Label order everywhere: **BUG, DECISION, TASK, LEARNING**.
Primary accuracy = correct / **total** (invalid counted wrong). Valid-only accuracy
is a secondary metric only.

| Metric | Task 87 (prompt-only) | Task 88 (LoRA) |
|---|---:|---:|
| Base model | `llama3.2:1b` (Ollama) | `HuggingFaceTB/SmolLM2-135M` + LoRA |
| Test total / valid / invalid | 12 / **0** / 12 | 12 / **12** / 0 |
| **Primary accuracy** | 0.0 | **0.0833** (1/12) |
| Valid-output rate | 0.0 | 1.0 |
| Macro F1 | 0.0 | 0.0385 |
| Latency mean / median (ms) | 545.28 / 520.24 | 126.31 / 111.7 |
| Error categories | `invalid_format: 12` | none |

Task 88 per-class (P / R / F1, support): BUG 0/0/0 (4) · DECISION 0/0/0 (3) ·
**TASK 0.0833 / 1.0 / 0.1538 (1)** · LEARNING 0/0/0 (4). The single correct
prediction was the lone `TASK` example; the fine-tuned model **over-predicts TASK**
for nearly every input.

Task 88 training summary (from `run_metadata.json`): LoRA rank 16, alpha 32,
dropout 0.05, targets `q/k/v/o/gate/up/down_proj`; lr 2e-4, batch 4, grad-accum 2,
2 epochs, seq 128, seed 42, fp32; train loss/epoch `[1.6226, 0.7226]`; duration
15.25 s; validation accuracy 3/11 (recorded at training time, not on the test set).

## 6. Reproducing Tasks 87–89

Use the existing virtual environments. Automated tests are fully offline
(monkeypatched `httpx` / deterministic mocks); only the separate live scripts touch
a running model.

```bash
cd backend

# Task 87/89 offline unit + regression tests (system python3.9)
python3 -m pytest tests/test_classification_task87_num_predict.py -q   # Task 90 fix
python3 -m pytest tests/test_classification_baseline.py -q             # Task 87 service
python3 -m pytest tests/test_classification_task89.py -q               # Task 89 evaluator

# Task 88 LoRA tests incl. real train+reload smoke test (isolated ML env)
.venv-ft/bin/python -m pytest tests/test_classification_lora.py -q

# Task 87 live baseline (needs local Ollama with llama3.2:1b; loopback only)
python3 -m app.scripts.run_classification_baseline

# Task 89 live comparison (needs .venv-ft deps + Task 88 adapter on disk)
.venv-ft/bin/python -m app.scripts.evaluate_lora_vs_baseline
```

Artifacts (read-only, preserved): `data/classification/results/baseline_predictions.jsonl`,
`baseline_report.json`, `baseline_report.txt`, `results/task89_comparison/task89_{predictions.jsonl,report.json,report.txt}`,
`experiments/lora_task88/`.

## 7. Production-integration decision (Task 90): DO NOT INTEGRATE

Decision: **keep both experimental classifiers OUT of the production query pipeline.**
Neither is enabled behind a flag or by default.

Rationale (evidence-based):

1. **Output validity is not classification correctness.** Task 88 emits a valid label
   100% of the time yet is correct 1/12 times; Task 87 emits a valid label 0% of the
   time. Valid formatting alone proves nothing about quality.
2. **Task 87's output-contract failure** (see §8) makes its current configuration
   unusable as a reliable classifier.
3. **Task 88's 1/12 accuracy** and systematic over-prediction of `TASK` do not meet
   any readiness threshold.
4. **The 12-example test set — with a single `TASK` example — cannot support
   generalization claims.** All per-class numbers here are directional only.
5. **Task 89 compares two different base models** (prompt-only `llama3.2:1b` vs LoRA
   `SmolLM2-135M`); it is a *system* comparison, **not** the isolated causal effect
   of LoRA.

Evidence that would be required before reconsidering integration:
- Fine-tuning measured on the **same base model** as the prompt baseline (controlled
  causal comparison), and
- A substantially larger, class-balanced corpus (especially `TASK`), and
- Held-out accuracy / macro-F1 materially above a trivial majority-class baseline on
  a test set large enough for stable per-class estimates, and
- A prompt-baseline fix so the comparison is formatting-fair.

## 8. Task 87 output-contract defect (fixed in Task 90, narrowly scoped)

- **Defect:** `OllamaBackend.infer` hard-coded `options.num_predict = 8`, which
  truncated the model response before a label token could be emitted — a verified
  contributor to Task 87's 12/12 `invalid_format` result.
- **Diagnosis:** raising the budget lets the model *finish* its response, but
  `llama3.2:1b` still does not obey the prompt's output contract (prompt echoing /
  label-listing) even at larger token limits. So the token cap is a **secondary
  formatting bug**, not the root cause of mis-classification.
- **Fix (implemented, default-off from the frozen result):** the generation budget is
  now a configurable constructor argument `OllamaBackend(max_new_tokens=...)` with a
  non-truncating default of **32**. The frozen Task 87 artifacts and prompt are
  **unchanged** and were **not** re-run; the test set was **not** tuned against.
- **Regression test:** `tests/test_classification_task87_num_predict.py` (offline;
  monkeypatches `httpx.post`) asserts the default is 32 (no longer 8) and that a
  configured value is carried through to the outgoing request.

## 9. Task 90 verification & regression results

Commands run (system `python3` = 3.9.6; ML env = `.venv-ft` Python 3.12):

| Command | Result |
|---|---|
| `python3 -m pytest tests/test_classification_task87_num_predict.py -q` | **5 passed** |
| `python3 -m pytest tests/test_classification_baseline.py -q` | **45 passed** |
| `python3 -m pytest tests/test_classification_task89.py -q` | **passed** |
| `python3 -m pytest <above three>` (combined) | **68 passed** |
| `.venv-ft/bin/python -m pytest tests/test_classification_lora.py -q` | **34 passed** (incl. real train+reload smoke test) |

**Preservation checks:** Task 86 `corpus.jsonl` and all `splits/*.jsonl` retain their
original mtimes (2026-10-13); Task 87 `results/`, Task 88 `adapter_model.bin`
(SHA-256 `e7fab36d…`), and Task 89 `task89_report.json` were byte-verified unchanged.

**Known broader-suite environment blockers (not Task 90 failures):** unrelated backend
tests (`test_vector_store.py`, `test_retrieval.py`, agent/DB tests) fail to collect
under system `python3.9` due to missing `sqlalchemy` / absent fixtures. None import the
classification modules; they are pre-existing and out of scope.

## 10. Limitations & next steps

- **Small dataset (56 total; 12 test; 1 test TASK).** No per-class generalization is
  supported. Expand the corpus before per-class claims.
- **Different base models across Task 87/88** → not a causal LoRA comparison.
- **Prompt-only baseline needs a real output-contract fix** (beyond the token budget)
  before it can produce valid labels for a formatting-fair comparison.
- **Next (Task 100+):** reproduce fine-tuning on the `llama3.2` base, enlarge and
  rebalance the corpus, then re-evaluate before any production integration.

