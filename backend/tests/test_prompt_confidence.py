"""Tasks 6.7/6.9 — retrieval confidence and evidence-grounded prompt tests.

Pure unit tests: no database, no network, no model. Confidence thresholds and
the evidence budget are plain configuration objects, so each rule is exercised
directly rather than through a live pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import pytest

from app.core.config import Settings
from app.services.prompt import (
    CONFIDENCE_NONE,
    CONFIDENCE_STRONG,
    CONFIDENCE_WEAK,
    assess_confidence,
    build_prompt,
)


@dataclass(frozen=True)
class _Item:
    """Minimal evidence stand-in: only the fields confidence logic reads."""

    similarity: float
    memory_id: str = "mem_a"
    chunk_id: str = "chk_a"
    passage: str = "A stored passage."


def config(**overrides) -> Settings:
    base = Settings(ollama_base_url="http://127.0.0.1:11434")
    return replace(base, **overrides) if overrides else base


# --- Confidence ------------------------------------------------------------


def test_no_matches_is_none_not_weak():
    """A successful search with no results is reported distinctly."""
    result = assess_confidence([], config())
    assert result.level == CONFIDENCE_NONE
    assert result.reason


def test_strong_requires_enough_passages_and_a_high_similarity():
    items = [_Item(similarity=0.9), _Item(similarity=0.8)]
    result = assess_confidence(items, config())
    assert result.level == CONFIDENCE_STRONG


def test_high_similarity_but_a_single_passage_is_only_weak():
    result = assess_confidence([_Item(similarity=0.95)], config())
    assert result.level == CONFIDENCE_WEAK
    assert "1" in result.reason


def test_a_barely_matching_set_is_weak():
    items = [_Item(similarity=0.26), _Item(similarity=0.26)]
    result = assess_confidence(items, config())
    assert result.level == CONFIDENCE_WEAK
    assert "threshold" in result.reason


def test_keyword_only_evidence_is_never_strong():
    """A BM25-only hit has no semantic corroboration, so it must read as weak."""
    items = [_Item(similarity=0.0), _Item(similarity=0.0), _Item(similarity=0.0)]
    result = assess_confidence(items, config())
    assert result.level == CONFIDENCE_WEAK
    assert "keywords only" in result.reason


def test_thresholds_are_configurable():
    items = [_Item(similarity=0.45), _Item(similarity=0.45)]
    assert assess_confidence(items, config(rag_confidence_strong=0.40)).level == (
        CONFIDENCE_STRONG
    )
    assert assess_confidence(items, config(rag_confidence_strong=0.99)).level == (
        CONFIDENCE_WEAK
    )


def test_min_evidence_for_strong_is_configurable():
    items = [_Item(similarity=0.9), _Item(similarity=0.9)]
    assert assess_confidence(items, config(rag_min_evidence_for_strong=2)).level == (
        CONFIDENCE_STRONG
    )
    assert assess_confidence(items, config(rag_min_evidence_for_strong=3)).level == (
        CONFIDENCE_WEAK
    )


# --- Prompt construction ---------------------------------------------------


def test_prompt_separates_question_from_evidence():
    prompt = build_prompt("How do HNSW graphs work?", [_Item(similarity=0.9)], config())
    assert "QUESTION:" in prompt
    assert "How do HNSW graphs work?" in prompt
    assert "BEGIN EVIDENCE" in prompt
    assert "END EVIDENCE" in prompt
    # The question must appear before the evidence block, not inside it.
    assert prompt.index("QUESTION:") < prompt.index("BEGIN EVIDENCE")


def test_prompt_marks_evidence_as_untrusted_data():
    prompt = build_prompt("anything", [_Item(similarity=0.9)], config())
    assert "untrusted data" in prompt
    assert "never as" in prompt and "instructions" in prompt


def test_prompt_carries_stable_evidence_identifiers():
    item = _Item(similarity=0.9, memory_id="mem_abc", chunk_id="chk_xyz")
    prompt = build_prompt("anything", [item], config())
    assert "memory_id=mem_abc" in prompt
    assert "chunk_id=chk_xyz" in prompt
    assert "[1]" in prompt


def test_prompt_asks_for_citations_and_admits_missing_answers():
    prompt = build_prompt("anything", [_Item(similarity=0.9)], config())
    assert "Cite evidence" in prompt
    assert "say so plainly" in prompt


def test_prompt_is_empty_when_there_is_no_evidence():
    """An empty evidence block would invite the model to answer from nothing."""
    assert build_prompt("anything", [], config()) == ""


def test_prompt_enforces_the_evidence_budget_without_truncating_passages():
    items = [
        _Item(similarity=0.9, memory_id=f"mem_{n}", chunk_id=f"chk_{n}", passage="x" * 500)
        for n in range(10)
    ]
    settings = config(rag_evidence_budget_chars=1200)
    prompt = build_prompt("anything", items, settings)

    # Budget applies to the evidence block only, and the first passage is always
    # kept even if it alone is large.
    evidence = prompt.split("BEGIN EVIDENCE (untrusted data) ---\n")[1].split(
        "\n--- END EVIDENCE ---"
    )[0]
    assert len(evidence) <= settings.rag_evidence_budget_chars + 500
    # Whole passages only: every retained block is intact.
    assert "x" * 500 in evidence
    assert "mem_0" in evidence


def test_prompt_keeps_the_highest_ranked_evidence_first():
    items = [
        _Item(similarity=0.9, memory_id="mem_first"),
        _Item(similarity=0.5, memory_id="mem_second"),
    ]
    prompt = build_prompt("anything", items, config(rag_evidence_budget_chars=140))
    assert prompt.index("mem_first") < prompt.index("mem_second")


@pytest.mark.parametrize("budget", [0, -1])
def test_prompt_rejects_a_nonsensical_budget(budget):
    with pytest.raises((ValueError, AssertionError)):
        build_prompt("q", [_Item(similarity=0.9)], config(rag_evidence_budget_chars=budget))
