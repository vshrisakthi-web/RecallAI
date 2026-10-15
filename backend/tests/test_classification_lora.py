"""Classification LoRA tests for Task 88.

Two groups:
1. Task-data + config tests (torch-free).  These run now, before the approved
   ML pip install.
2. A deterministic mock-smoke group that exercises the full pipeline
   orchestration with stubs (no weights, no real model).  A separate,
   explicitly flagged test class (`TestTrainerRealSmoke`) is skipped unless
   torch/transformers/peft are actually installed.

Run from backend/ (so `data` and `app` resolve)::

    python -m pytest tests/ -v
"""

import json
from pathlib import Path

import pytest

from data.classification import dataset as ds
from data.classification.dataset import (
    DATASET_VERSION,
    SEED as DATASET_SEED,
    ALLOWED_LABELS,
    ALLOWED_LABELS as DATASET_ALLOWED_LABELS,
    load_corpus,
    load_split,
    load_splits,
    split_sizes,
    validate_corpus,
    validate_dataset,
    validate_splits,
    count_examples_per_label,
)

from app.scripts.configs.lora_config import (
    BASE_MODEL_ID,
    BASE_MODEL_REVISION,
    LORA_RANK,
    LORA_ALPHA,
    LORA_DROPOUT,
    LORA_TARGET_MODULES,
    INITIAL_LR,
    TRAIN_BATCH_SIZE,
    GRAD_ACCUM,
    EPOCHS,
    MAX_SEQ_LENGTH,
    SEED as CFG_SEED,
    ALLOWED_LABELS as CFG_ALLOWED_LABELS,
    LoRAConfig,
    _default_config,
)

from app.scripts import train_classification_lora as trainer


# --------------------------------------------------------------------------- #
# Task data
# --------------------------------------------------------------------------- #
class TestDatasetConstants:
    def test_dataset_version_and_seed(self):
        assert DATASET_VERSION == "1.0"
        assert DATASET_SEED == 42
        assert DATASET_ALLOWED_LABELS == ["BUG", "DECISION", "TASK", "LEARNING"]

    def test_corpus_is_balanced(self):
        corpus = load_corpus()
        assert len(corpus) == 56
        assert dict(count_examples_per_label(corpus)) == {
            "BUG": 14, "DECISION": 14, "TASK": 14, "LEARNING": 14
        }
        assert {r["provenance"] for r in corpus} == {"synthetic"}


class TestDatasetLoading:
    def test_load_corpus(self):
        assert len(load_corpus()) == 56

    def test_split_sizes(self):
        assert split_sizes() == {"train": 33, "validation": 11, "test": 12}

    def test_load_single_split(self):
        train = load_split("train")
        assert len(train) == 33
        assert [r["example_id"] for r in train] == sorted(
            r["example_id"] for r in train
        )

    def test_unknown_split_raises(self):
        with pytest.raises(ValueError):
            load_split("dev")


class TestDatasetValidation:
    def test_real_dataset_passes(self):
        errors = validate_dataset()
        assert errors == {"corpus": [], "splits": [], "warnings": []}

    def test_validate_corpus_empty_on_real_data(self):
        errors, warnings = validate_corpus(load_corpus())
        assert errors == []
        assert warnings == []

    def test_validate_splits_empty_on_real_data(self):
        splits = load_splits()
        errors, warnings = validate_splits(splits)
        assert errors == []
        assert warnings == []

    def test_label_distribution_train(self):
        train = load_split("train")
        assert dict(count_examples_per_label(train)) == {
            "BUG": 7, "DECISION": 9, "TASK": 10, "LEARNING": 7
        }

    def test_invalid_corpus_is_flagged(self):
        bad_corpus = [
            {"example_id": "a", "text": "ok", "label": "BAD", "provenance": "synthetic"},
            {"example_id": "a", "text": "dup", "label": "BUG", "provenance": "synthetic"},
            {"example_id": "b", "text": "", "label": "BUG", "provenance": "synthetic"},
        ]
        errors, _ = validate_corpus(bad_corpus)
        assert len(errors) >= 3


class TestDatasetGoldLabelIsolation:
    """Feeding rules: labels live in their own field and are never mixed into text."""

    def test_text_is_original_corpus_text(self):
        corpus = load_corpus()
        by_id = {r["example_id"]: r for r in corpus}
        train = load_split("train")
        for rec in train:
            source = by_id[rec["example_id"]]
            assert rec["text"] == source["text"]
            assert rec["label"] == source["label"]

    def test_load_split_does_not_build_prompts_or_append_labels(self):
        train = load_split("train")
        sample = train[0]
        by_id = {r["example_id"]: r for r in load_corpus()}
        source = by_id[sample["example_id"]]
        assert sample["text"] == source["text"]
        assert sample["label"] == source["label"]
        assert "OUTPUT" not in sample["text"].upper()

class TestConfigDefaults:
    def test_spec_values(self):
        cfg = _default_config()
        assert cfg.rank == 16
        assert cfg.alpha == 32
        assert cfg.dropout == 0.05
        assert list(cfg.target_modules) == [
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ]
        assert cfg.lr == 2e-4
        assert cfg.weight_decay == 0.0
        assert cfg.train_batch_size == 4
        assert cfg.grad_accum == 2
        assert cfg.epochs == 2
        assert cfg.max_seq_length == 128
        assert cfg.seed == 42
        assert cfg.fp16 is False
        assert cfg.bf16 is False

    def test_base_model_is_ungated_smollm2(self):
        cfg = _default_config()
        assert BASE_MODEL_ID == "HuggingFaceTB/SmolLM2-135M"
        assert BASE_MODEL_REVISION == "main"
        assert cfg.resolve_base_model() == "HuggingFaceTB/SmolLM2-135M"


class TestConfigRoundTrip:
    def test_to_from_dict_returns_identical(self):
        cfg = _default_config()
        loaded = LoRAConfig.from_dict(cfg.to_dict())
        assert loaded == cfg


class TestConfigValidity:
    def test_valid_config_is_empty(self):
        assert _default_config().validate() == []

    @pytest.mark.parametrize(
        "rank,alpha,msg",
        [
            (0, 32, "rank 0"),
            (8, 8, "alpha <= rank"),
            (32, 16, "alpha < rank"),
            (16, 8, "alpha < rank"),
        ],
    )
    def test_invalid_lora_bounds(self, rank, alpha, msg):
        cfg = LoRAConfig(rank=rank, alpha=alpha)
        assert cfg.validate(), msg

    def test_dropout_out_of_range(self):
        assert LoRAConfig(dropout=1.0).validate()
        assert LoRAConfig(dropout=-0.1).validate()

    def test_batch_not_divisible_by_grad_accum(self):
        assert LoRAConfig(train_batch_size=5, grad_accum=2).validate()


class TestConfigBaseModel:
    def test_resolve_base_model(self):
        assert BASE_MODEL_ID == "HuggingFaceTB/SmolLM2-135M"

    def test_target_modules_nonempty(self):
        assert len(LORA_TARGET_MODULES) == 7


class TestTrainerImportGuard:
    def test_module_imports_without_torch(self):
        # The trainer module must import cleanly regardless of whether torch is
        # installed; the HAS_* flags simply reflect the current environment.
        assert isinstance(trainer.HAS_TORCH, bool)
        assert isinstance(trainer.HAS_TRANSFORMERS, bool)
        assert isinstance(trainer.HAS_PEFT, bool)

    def test_require_ml_raises_when_unavailable(self, monkeypatch):
        # Force the "ML not installed" state and confirm the guard raises.
        monkeypatch.setattr(trainer, "HAS_TORCH", False)
        monkeypatch.setattr(trainer, "HAS_TRANSFORMERS", False)
        monkeypatch.setattr(trainer, "HAS_PEFT", False)
        with pytest.raises(RuntimeError):
            trainer._require_ml()

    def test_require_ml_ok_when_available(self, monkeypatch):
        monkeypatch.setattr(trainer, "HAS_TORCH", True)
        monkeypatch.setattr(trainer, "HAS_TRANSFORMERS", True)
        monkeypatch.setattr(trainer, "HAS_PEFT", True)
        trainer._require_ml()  # must not raise

    def test_cli_parses(self):
        ns = trainer.parse_args(["--config", "/x", "--out-dir", "/y"])
        assert str(ns.config) == "/x"
        assert ns.train_split == "train"
        assert ns.val_split == "validation"
        assert str(ns.out_dir) == "/y"


class TestTrainerMockSmoke:
    """Deterministic, torch-free smoke tests for the metadata/disk contracts."""

    class _FakeModel:
        def __init__(self):
            self.saved = False

        def __call__(self, **_batch):
            return None

        def save_pretrained(self, *args, **kwargs):
            self.saved = True
            if args:
                args[0].joinpath("adapter_model.bin").touch()

    class _FakeTokenizer:
        def save_pretrained(self, *args, **kwargs):
            self.saved = True

    def test_metadata_assembly_contract(self):
        cfg = _default_config()
        metadata = trainer._build_metadata(
            cfg,
            Path("/tmp/lora_task88"),
            [{"example_id": "bug_0", "text": "x", "label": "BUG"}],
            [{"example_id": "bug_1", "text": "y", "label": "DECISION"}],
            {"num_examples": 1, "mean_loss": 0.0},
            ml_available=False,
        )
        assert metadata["dataset_version"] == "1.0"
        assert metadata["train_size"] == 1
        assert metadata["val_size"] == 1
        assert metadata["metrics"] == {"num_examples": 1, "mean_loss": 0.0}
        assert metadata["environment"]["ml_available"] is False
        assert cfg.resolve_base_model() == "HuggingFaceTB/SmolLM2-135M"

    def test_save_checkpoint_writes_adapter_and_tokenizer(self, tmp_path):
        cfg = _default_config()
        out_dir = tmp_path / "lora_task88"
        trainer.save_checkpoint(out_dir, self._FakeModel(), self._FakeTokenizer(), cfg, {"num_examples": 0})
        assert out_dir.exists()
        assert (out_dir / "adapter_model.bin").exists()
        assert (out_dir / "adapter_config.json").exists()
        assert (out_dir / "training_args.json").exists()

        adapter_config = json.loads((out_dir / "adapter_config.json").read_text(encoding="utf-8"))
        assert adapter_config["base_model_id"] == cfg.base_model_id
        assert adapter_config["lora"]["rank"] == cfg.rank
        training_args = json.loads((out_dir / "training_args.json").read_text(encoding="utf-8"))
        assert training_args["learning_rate"] == cfg.lr


class TestTrainerRealSmoke:
    """Real end-to-end smoke test (CPU). Only run after approvals + install."""

    def test_run_pipeline_saves_adapter_and_metadata(self, tmp_path):
        pytest.importorskip("transformers", reason="requires ML extras (transformers/torch)")
        from transformers import AutoModelForCausalLM, AutoTokenizer

        cfg = _default_config()
        records = [
            {"example_id": f"bug_{i}", "text": f"sample {i}", "label": "BUG"}
            for i in range(3)
        ]
        out_dir = tmp_path / "lora_task88"

        tokenizer = AutoTokenizer.from_pretrained(
            cfg.base_model_id, revision=cfg.base_model_revision
        )
        model, _ = trainer.build_model_and_tokenizer(cfg)

        metadata = trainer.run_pipeline(cfg, out_dir, records, [])

        assert out_dir.exists()
        assert (out_dir / "adapter_model.bin").exists()
        assert (out_dir / "adapter_config.json").exists()
        assert metadata["train_size"] == 3
        assert metadata["environment"]["ml_available"] is True
        # New Phase 6 metadata fields must be present on a real run.
        assert "training_duration_seconds" in metadata
        assert metadata["split_roles"]["held_out_and_not_used"] == "test"
        assert metadata["environment"]["transformers"]
        assert metadata["base_model_id"] == "HuggingFaceTB/SmolLM2-135M"

    def test_saved_adapter_reloads_and_infers_label(self, tmp_path):
        """Train -> save -> reload the adapter -> generate a single label."""
        pytest.importorskip("transformers", reason="requires ML extras (transformers/torch)")
        pytest.importorskip("peft", reason="requires peft")
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer

        cfg = _default_config()
        records = [
            {"example_id": f"bug_{i}", "text": f"the build crashed with error {i}", "label": "BUG"}
            for i in range(3)
        ]
        out_dir = tmp_path / "lora_task88"
        trainer.run_pipeline(cfg, out_dir, records, [])

        # Reload base + adapter exactly as a downstream consumer would.
        tokenizer = AutoTokenizer.from_pretrained(cfg.base_model_id)
        base = AutoModelForCausalLM.from_pretrained(cfg.base_model_id)
        reloaded = PeftModel.from_pretrained(base, str(out_dir))
        reloaded.eval()

        # predict_label must return a valid label (or the honest "INVALID"
        # sentinel) — never crash — using the exact Task 89 inference path.
        label = trainer.predict_label(reloaded, tokenizer, "the server returns 500 on upload")
        assert label in trainer.CLASSIFY_LABELS + ["INVALID"]




    def test_no_gold_field_in_records(self):
        train = load_split("train")
        assert not any("gold" in r for r in train)
