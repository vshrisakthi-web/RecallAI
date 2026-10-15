"""Classification baseline tests for Task 87."""
import pytest

from app.services.classification import (
    ClassificationService, ClassificationReport, ClassificationConfig,
    DeterministicMockBackend, TimeoutMockBackend,
    load_corpus, load_split, build_prompt, parse_prediction,
    prompt_fingerprint, create_classification_service, ALLOWED_LABELS,
)


class TestPromptFormat:
    def test_prompt_template_exists(self):
        template = build_prompt("")
        assert "CLASS_PROMPT_v20241014_01" in template
        assert "BUG" in template
        assert "DECISION" in template
        assert "TASK" in template
        assert "LEARNING" in template

    def test_prompt_has_correct_format(self):
        template = build_prompt("test input")
        lines = template.strip().split("\n")
        assert lines[0] == "VERSION: CLASS_PROMPT_v20241014_01"


class TestParsePrediction:
    def test_parse_valid_label_uppercase(self):
        label, err = parse_prediction("BUG")
        assert label == "BUG"
        assert err is None

    def test_parse_valid_label_lowercase(self):
        label, err = parse_prediction("bug")
        assert label == "BUG"

    def test_parse_invalid_format(self):
        label, err = parse_prediction("This is not a valid label")
        assert label is None
        assert err == "invalid_format"

    def test_parse_empty_response(self):
        label, err = parse_prediction("")
        assert label is None
        assert err == "empty_response"

    def test_parse_marked_code_fences(self):
        label, err = parse_prediction("```BUG```")
        assert label == "BUG"
        assert err is None

    def test_parse_single_label_only(self):
        label, err = parse_prediction("BUG prediction")
        assert label is None


class TestDeterministicMockBackend:
    def test_mock_always_returns_canned_label(self):
        backend = DeterministicMockBackend(canned_label="DECISION")
        assert backend.infer("text") == "DECISION"

    def test_mock_calls_recorded(self):
        backend = DeterministicMockBackend(canned_label="BUG")
        backend.infer("text 1")
        backend.infer("text 2")
        assert len(backend.calls) == 2


class TestTimeoutMockBackend:
    def test_timeout_raises(self):
        backend = TimeoutMockBackend()
        with pytest.raises(TimeoutError):
            backend.infer("text")


class TestClassificationConfig:
    def test_config_defaults(self):
        config = ClassificationConfig()
        assert config.model_id == "mock:deterministic"
        assert config.timeout_seconds == 30.0
        assert config.max_retries == 2
        assert config.prompt_version == "CLASS_PROMPT_v20241014_01"


class TestClassificationServiceFactory:
    def test_factory_creates_service(self):
        svc = create_classification_service()
        assert isinstance(svc, ClassificationService)

    def test_factory_with_custom_model_id(self):
        svc = create_classification_service(model_id="test-model")
        assert svc._config.model_id == "test-model"


class TestServiceClassifyText:
    def test_classify_bug_keywords(self):
        svc = create_classification_service()
        assert svc.classify_text("The app crashes") == "BUG"

    def test_classify_decision_keywords(self):
        svc = create_classification_service()
        assert svc.classify_text("The team decided") == "DECISION"

    def test_classify_task_keywords(self):
        svc = create_classification_service()
        assert svc.classify_text("Write unit tests") == "TASK"

    def test_classify_learning_keywords(self):
        svc = create_classification_service()
        text = "Learn about database indexing"
        assert svc.classify_text(text) == "LEARNING"


class TestServicePredict:
    def test_predict_structure(self):
        svc = create_classification_service()
        example = {"example_id": "test_001", "text": "Bug in the system", "label": "BUG"}
        pred = svc.predict(example)
        required_fields = [
            "dataset_version", "split_name", "example_id",
            "gold_label", "predicted_label", "is_valid_output",
            "error_category", "inference_latency_ms",
            "model_id", "prompt_version", "prompt_fingerprint",
            "evaluation_timestamp"
        ]
        for field in required_fields:
            assert field in pred, f"Missing: {field}"

    def test_predict_valid_output(self):
        svc = create_classification_service()
        example = {"example_id": "test_001", "text": "Error in the API", "label": "BUG"}
        pred = svc.predict(example)
        assert pred["is_valid_output"] is True
        assert pred["predicted_label"] == "BUG"
        assert pred["error_category"] is None

    def test_predict_invalid_output(self):
        svc = create_classification_service(model=TimeoutMockBackend())
        example = {"example_id": "test_001", "text": "Some text", "label": "BUG"}
        pred = svc.predict(example)
        assert pred["is_valid_output"] is False
        assert "inference_error" in pred["error_category"]


class TestServiceEvaluateSplit:
    def test_evaluate_split_returns_report(self):
        svc = create_classification_service()
        report, predictions = svc.evaluate_split("test")
        assert isinstance(report, ClassificationReport)
        assert len(predictions) == 12

    def test_report_has_all_metrics(self):
        svc = create_classification_service()
        report, _ = svc.evaluate_split("test")
        assert report.total == 12
        assert report.valid + report.invalid == report.total
        assert 0.0 <= report.accuracy <= 1.0
        assert 0.0 <= report.macro_f1 <= 1.0
        assert len(report.precision) == 4
        assert len(report.recall) == 4
        assert len(report.f1) == 4
        assert len(report.confusion_matrix) == 4

    def test_confusion_matrix_fixed_order(self):
        svc = create_classification_service()
        report, _ = svc.evaluate_split("test")
        expected = ["BUG", "DECISION", "TASK", "LEARNING"]
        assert list(report.confusion_matrix.keys()) == expected
        for g in expected:
            assert list(report.confusion_matrix[g].keys()) == expected


class TestMetricsCalculations:
    def test_accuracy_computation(self):
        svc = create_classification_service()
        predictions = []
        for i in range(12):
            pred = svc.predict({
                "example_id": f"ex_{i}",
                "text": f"text {i}",
                "label": "BUG" if i < 4 else "DECISION",
            })
            predictions.append(pred)
        report, _ = svc._compute_metrics(predictions, "test")
        assert report.total == 12


class TestPerClassMetrics:
    def test_per_class_metrics_exist(self):
        svc = create_classification_service()
        report, _ = svc.evaluate_split("test")
        for label in ALLOWED_LABELS:
            assert label in report.precision
            assert label in report.recall
            assert label in report.f1
            assert 0.0 <= report.precision[label] <= 1.0
            assert 0.0 <= report.recall[label] <= 1.0
            assert 0.0 <= report.f1[label] <= 1.0


class TestConfusionMatrix:
    def test_confusion_matrix_shape(self):
        svc = create_classification_service()
        report, _ = svc.evaluate_split("test")
        assert len(report.confusion_matrix) == 4
        for gold in ALLOWED_LABELS:
            for pred_label in ALLOWED_LABELS:
                val = report.confusion_matrix[gold][pred_label]
                assert isinstance(val, int)
                assert val >= 0

    def test_diagonal_sum_le_valid(self):
        svc = create_classification_service()
        report, _ = svc.evaluate_split("test")
        diag = sum(report.confusion_matrix[l][l] for l in ALLOWED_LABELS)
        assert diag <= report.valid


class TestLatencyStatistics:
    def test_latency_stats_present(self):
        svc = create_classification_service()
        report, _ = svc.evaluate_split("test")
        assert report.latency_mean_ms >= 0
        assert report.latency_median_ms >= 0


class TestFailedPredictions:
    def test_failed_predictions_count(self):
        svc = create_classification_service()
        report, _ = svc.evaluate_split("test")
        assert 0 <= report.failed_predictions <= report.total


class TestErrorCategories:
    def test_error_categories_with_mock(self):
        svc = create_classification_service()
        report, _ = svc.evaluate_split("test")
        assert len(report.error_categories) == 0

    def test_error_categories_with_timeout(self):
        svc = create_classification_service(model=TimeoutMockBackend())
        report, _ = svc.evaluate_split("test")
        assert len(report.error_categories) > 0


class TestReproducibility:
    def test_deterministic_mock_consistent(self):
        backend = DeterministicMockBackend(canned_label="BUG")
        assert backend.infer("p1") == backend.infer("p2")

    def test_prompt_fingerprint_consistent(self):
        assert prompt_fingerprint() == prompt_fingerprint()


class TestGoldLabelIsolation:
    def test_gold_label_not_sent_to_model(self):
        svc = create_classification_service()
        example = {"example_id": "gold_test", "text": "bug found", "label": "BUG"}
        pred = svc.predict(example, gold_label="DECISION")
        assert pred["gold_label"] == "BUG"
        assert pred["predicted_label"] == "BUG"


class TestSplitSelection:
    def test_train_val_test_sizes(self):
        assert len(load_split("train")) == 33
        assert len(load_split("validation")) == 11
        assert len(load_split("test")) == 12


class TestLabelDefinitions:
    def test_all_four_labels_in_prompt(self):
        template = build_prompt("")
        assert "BUG:" in template
        assert "DECISION:" in template
        assert "TASK:" in template
        assert "LEARNING:" in template


class TestOutputContract:
    def test_output_only_label_name(self):
        label, _ = parse_prediction("BUG extra text")
        assert label is None
        label, _ = parse_prediction("BUG")
        assert label == "BUG"
        label, _ = parse_prediction("  BUG  ")
        assert label == "BUG"


class TestVersionedPrompt:
    def test_prompt_is_versioned(self):
        fp = prompt_fingerprint()
        assert len(fp) == 64
        assert fp == prompt_fingerprint()

    def test_prompt_version_constant(self):
        from app.services.classification import PROMPT_VERSION
        assert PROMPT_VERSION == "CLASS_PROMPT_v20241014_01"


class TestDatasetMetadata:
    def test_report_has_dataset_version(self):
        svc = create_classification_service()
        report, _ = svc.evaluate_split("test")
        assert report.dataset_version == "1.0"

    def test_report_has_prompt_version(self):
        svc = create_classification_service()
        report, _ = svc.evaluate_split("test")
        assert report.prompt_version == "CLASS_PROMPT_v20241014_01"

    def test_report_has_prompt_fingerprint(self):
        svc = create_classification_service()
        report, _ = svc.evaluate_split("test")
        assert len(report.prompt_fingerprint) == 64

    def test_report_has_model_id(self):
        svc = create_classification_service(model_id="test-model-42")
        report, _ = svc.evaluate_split("test")
        assert report.model_id == "test-model-42"


class TestLimitationDocumentation:
    def test_task_single_example_limit(self):
        """Per dataset spec: test split has 1 TASK example."""
        test_examples = load_split("test")
        task_examples = [ex for ex in test_examples if ex["label"] == "TASK"]
        assert len(task_examples) == 1
        assert task_examples[0]["example_id"] == "task_011"
