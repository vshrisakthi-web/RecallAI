"""Task 6.10 — retrieval evaluation tests.

The dataset is synthetic and the vectors are fixed, so these tests are fully
offline: no private data, no database, and no embedding model. Reported metric
values below are **measured from this dataset** by this test run.
"""

from __future__ import annotations

import pytest

from app.services.evaluation import (
    DELETED_MEMORY_ID,
    build_dataset,
    evaluate,
    format_report,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


@pytest.fixture(scope="module")
def dataset():
    return build_dataset()


@pytest.fixture(scope="module")
def report(dataset):
    corpus, cases = dataset
    return evaluate(corpus, cases, k=5)


# --- Metric correctness (known answers, not approximations) ---------------


def test_recall_at_k_is_the_fraction_of_relevant_found():
    assert recall_at_k(["a", "b"], {"a"}, 5) == 1.0
    assert recall_at_k(["x", "y"], {"a"}, 5) == 0.0
    assert recall_at_k(["a"], {"a", "b"}, 5) == 0.5


def test_recall_at_k_respects_the_cutoff():
    # "b" is relevant but sits below the cutoff, so it counts as missed.
    assert recall_at_k(["x", "b"], {"a", "b"}, 1) == 0.0


def test_recall_with_no_relevant_documents_is_perfect():
    """When nothing should be found, there is nothing to miss."""
    assert recall_at_k([], set(), 5) == 1.0


def test_precision_at_k_is_the_fraction_returned_that_is_relevant():
    assert precision_at_k(["a", "x"], {"a"}, 5) == 0.5
    assert precision_at_k(["a", "b"], {"a", "b"}, 5) == 1.0
    assert precision_at_k([], {"a"}, 5) == 0.0


def test_precision_at_k_respects_the_cutoff():
    assert precision_at_k(["a", "x", "y"], {"a"}, 2) == 0.5


def test_reciprocal_rank_scores_the_first_hit_highest():
    assert reciprocal_rank(["a"], {"a"}) == 1.0
    assert reciprocal_rank(["x", "a"], {"a"}) == 0.5
    assert reciprocal_rank(["x", "y", "a"], {"a"}) == pytest.approx(1 / 3)


def test_reciprocal_rank_is_zero_when_nothing_relevant_is_found():
    assert reciprocal_rank(["x", "y"], {"a"}) == 0.0


def test_metrics_never_return_nan_for_empty_inputs():
    assert recall_at_k([], set(), 5) == 1.0
    assert precision_at_k([], set(), 5) == 0.0
    assert reciprocal_rank([], {"a"}) == 0.0


# --- Dataset coverage -----------------------------------------------------


def test_dataset_covers_every_required_case_kind(dataset):
    _corpus, cases = dataset
    kinds = {case.kind for case in cases}
    assert kinds == {
        "exact",
        "paraphrase",
        "temporal",
        "source_filtered",
        "irrelevant",
        "duplicate",
        "deleted",
        "missing_metadata",
    }


def test_dataset_includes_negative_cases(dataset):
    _corpus, cases = dataset
    assert any(case.expect_empty for case in cases)


def test_dataset_is_deterministic(dataset):
    """Rebuilding must produce identical data so results are comparable."""
    corpus_a, cases_a = build_dataset()
    corpus_b, cases_b = build_dataset()
    assert [c.memory_id for c in corpus_a] == [c.memory_id for c in corpus_b]
    assert [c.case_id for c in cases_a] == [c.case_id for c in cases_b]
    assert [c.query_vector for c in cases_a] == [c.query_vector for c in cases_b]


# --- Measured retrieval behaviour ----------------------------------------


def test_deleted_memory_is_absent_from_every_result(report):
    """A deleted memory must never be retrievable, in any case."""
    for result in report.results:
        assert DELETED_MEMORY_ID not in result.retrieved


def test_negative_cases_return_nothing(report):
    """Irrelevant, out-of-window, wrong-source, and deleted cases must be empty."""
    for result in report.results:
        if result.kind in {"irrelevant", "temporal", "source_filtered", "deleted"}:
            if result.detail.startswith("expected no evidence"):
                assert result.retrieved == [], result.case_id


def test_every_positive_case_finds_its_relevant_memory(report):
    for result in report.results:
        if not result.detail.startswith("expected no evidence"):
            assert result.recall_at_k == 1.0, result.case_id


def test_exact_case_ranks_the_relevant_memory_first(report):
    result = next(r for r in report.results if r.case_id == "exact_token")
    assert result.retrieved[0] == "mem_vector_1"
    assert result.reciprocal_rank == 1.0


def test_paraphrase_case_is_found_by_semantics_alone(report):
    """The question shares no tokens with the corpus, so only vectors can win."""
    result = next(r for r in report.results if r.case_id == "paraphrase")
    assert "mem_vector_1" in result.retrieved


def test_source_filter_excludes_other_source_types(report):
    result = next(r for r in report.results if r.case_id == "source_filter_excludes_note")
    assert result.retrieved == []


def test_all_cases_pass_and_metrics_are_reported(report):
    """Guards the dataset: any regression fails here with the measured numbers."""
    assert report.failed == 0, format_report(report)
    assert report.mean_recall_at_k > 0.0
    assert report.mean_reciprocal_rank > 0.0


def test_report_metrics_are_within_valid_ranges(report):
    assert 0.0 <= report.mean_recall_at_k <= 1.0
    assert 0.0 <= report.mean_precision_at_k <= 1.0
    assert 0.0 <= report.mean_reciprocal_rank <= 1.0


def test_empty_report_means_are_zero_not_nan():
    from app.services.evaluation import EvaluationReport

    empty = EvaluationReport(results=[])
    assert empty.mean_recall_at_k == 0.0
    assert empty.mean_precision_at_k == 0.0
    assert empty.mean_reciprocal_rank == 0.0
    assert empty.total == 0


def test_format_report_includes_the_measured_metrics(report):
    text = format_report(report, k=5)
    assert "Recall@5" in text
    assert "Precision@5" in text
    assert "MRR" in text
    assert f"{report.passed}/{report.total}" in text
