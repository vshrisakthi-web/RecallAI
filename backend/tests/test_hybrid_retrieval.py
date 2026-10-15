"""Task 6.5 — hybrid retrieval and reciprocal rank fusion tests.

Fully offline: the embedding service uses a fake transport returning fixed
vectors, and "now" is injected. Covers semantic-only, keyword-only, overlapping,
and empty results; RRF ranking and determinism; consistent filtering; deleted
memory exclusion; and what happens when one channel fails.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.repositories.base import StorageError
from app.repositories.chunk_store import ChunkRepository
from app.repositories.sqlite_store import MemoryRepository
from app.repositories.vector_store import VectorStore
from app.services.chunking import chunk_text
from app.services.embeddings import EmbeddingService
from app.services.evidence import (
    KEYWORD_CHANNEL,
    SEMANTIC_CHANNEL,
    RetrievalInputError,
    RetrievalUnavailableError,
    fuse_rankings,
)
from app.services.hybrid import HybridRetrievalService
from app.services.keyword_search import KeywordSearchService
from tests._factories import make_record, utcnow

NOW = datetime(2026, 10, 12, 12, 0, 0, tzinfo=timezone.utc)
MODEL = "unit-embed-model"

# Fixed 3-dim vectors: "RAG-like" ~= [1,0,0], "cooking-like" ~= [0,1,0].
RAG_VEC = [1.0, 0.05, 0.0]
COOK_VEC = [0.0, 1.0, 0.0]
QUERY_VEC = [0.95, 0.1, 0.0]


def make_embeddings(vector, model=MODEL, failing=False):
    """Fake-transport embedding service returning a fixed query vector."""

    def fake_post(url: str, **kwargs):
        if failing:
            raise httpx.ConnectError("refused", request=httpx.Request("POST", url))
        inputs = kwargs["json"]["input"]
        return httpx.Response(
            200,
            json={"embeddings": [list(vector) for _ in inputs]},
            request=httpx.Request("POST", url),
        )

    config = Settings(ollama_base_url="http://127.0.0.1:11434", embedding_model=model)
    return EmbeddingService(config=config, post=fake_post), config


def seed(repository, sessions, memory_id, text, vector, captured_at=None, **kwargs):
    """Save a memory, index its chunks, and store a vector for each chunk."""
    saved, _ = repository.save_or_get(
        make_record(
            id=memory_id,
            _text=text,
            captured_at=captured_at or utcnow(),
            **kwargs,
        )
    )
    chunk_ids = ChunkRepository(sessions).replace_memory_chunks(
        saved.id, chunk_text(saved.normalized_text, saved.id)
    )
    VectorStore(sessions).upsert_many(
        [(cid, saved.id, list(vector)) for cid in chunk_ids], MODEL
    )
    return saved, chunk_ids


def make_service(
    repository,
    database_engine,
    vector=QUERY_VEC,
    model=MODEL,
    failing=False,
    **config,
):
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    embeddings, base = make_embeddings(vector, model, failing)
    # Settings is frozen, so overrides go through dataclasses.replace.
    settings_obj = replace(base, **config) if config else base
    service = HybridRetrievalService(
        memories=repository,
        chunks=ChunkRepository(sessions),
        vectors=VectorStore(sessions),
        embeddings=embeddings,
        keywords=KeywordSearchService(sessions),
        sessions=sessions,
        config=settings_obj,
        now=lambda: NOW,
    )
    return service, sessions


# --- RRF fusion (pure function) --------------------------------------------


def test_rrf_ranks_a_chunk_found_by_both_channels_highest():
    """Agreement between two independent methods is rewarded."""
    fused = fuse_rankings(
        semantic=[("chk_a", "mem_a", 0.9), ("chk_b", "mem_b", 0.8)],
        keyword=[("chk_a", "mem_a", 1), ("chk_c", "mem_c", 2)],
    )
    assert [c.chunk_id for c in fused] == ["chk_a", "chk_b", "chk_c"]
    assert set(fused[0].matched_by) == {SEMANTIC_CHANNEL, KEYWORD_CHANNEL}
    assert set(fused[1].matched_by) == {SEMANTIC_CHANNEL}
    assert set(fused[2].matched_by) == {KEYWORD_CHANNEL}


def test_rrf_deduplicates_a_chunk_listed_twice_in_one_channel():
    fused = fuse_rankings(
        semantic=[("chk_a", "mem_a", 0.9), ("chk_a", "mem_a", 0.5)],
        keyword=[("chk_a", "mem_a", 1), ("chk_a", "mem_a", 3)],
    )
    assert len(fused) == 1
    assert fused[0].keyword_rank == 1  # best (lowest) rank wins
    assert fused[0].similarity == 0.9  # best (highest) similarity wins


def test_rrf_is_deterministic_for_tied_scores():
    """Genuinely tied scores must break on chunk id, never on insertion order.

    A real tie: one chunk ranked 1st by the semantic channel and another ranked
    1st by the keyword channel both earn exactly weight/(k+1).
    """
    inputs = (
        [("chk_z", "mem_z", 0.5)],
        [("chk_a", "mem_a", 1)],
    )
    first = [c.chunk_id for c in fuse_rankings(*inputs)]
    for _ in range(5):
        assert [c.chunk_id for c in fuse_rankings(*inputs)] == first
    assert first == ["chk_a", "chk_z"]
    assert len({c.score for c in fuse_rankings(*inputs)}) == 1  # truly tied


def test_rrf_keyword_only_results_keep_zero_similarity():
    """A BM25 score is never reported as if it were a cosine similarity."""
    fused = fuse_rankings(semantic=[], keyword=[("chk_a", "mem_a", 1)])
    assert fused[0].similarity == 0.0
    assert fused[0].keyword_rank == 1


def test_rrf_zero_weight_disables_a_channel():
    fused = fuse_rankings(
        semantic=[("chk_a", "mem_a", 0.9)],
        keyword=[("chk_b", "mem_b", 1)],
        keyword_weight=0.0,
    )
    assert [c.chunk_id for c in fused] == ["chk_a"]


def test_rrf_rejects_a_non_positive_smoothing_constant():
    with pytest.raises(ValueError):
        fuse_rankings(semantic=[], keyword=[], rrf_k=0)


def test_rrf_empty_inputs_yield_no_candidates():
    assert fuse_rankings(semantic=[], keyword=[]) == []


# --- Hybrid service: the four required result shapes -----------------------


def test_overlapping_results_merge_into_one_evidence_item(repository, database_engine):
    """A chunk found by both channels must appear once, credited for both."""
    service, sessions = make_service(repository, database_engine)
    seed(
        repository, sessions, "mem_both",
        "HNSW graphs index embeddings for similarity search.",
        RAG_VEC, title="HNSW embeddings",
    )
    seed(repository, sessions, "mem_off", "Pasta needs salted boiling water.", COOK_VEC)

    result = service.retrieve("How do HNSW graphs index embeddings?")

    assert [e.memory_id for e in result.evidence] == ["mem_both"]
    top = result.evidence[0]
    assert set(top.matched_by) == {SEMANTIC_CHANNEL, KEYWORD_CHANNEL}
    assert top.keyword_rank == 1
    assert top.similarity > 0
    assert top.score > 0
    assert set(result.channels) == {SEMANTIC_CHANNEL, KEYWORD_CHANNEL}


def test_keyword_only_match_is_returned_when_semantics_find_nothing(
    repository, database_engine
):
    """Exact-token recall the embedding model cannot provide.

    The stored vector is orthogonal to the query vector, so the semantic
    channel scores it below the similarity floor and the keyword channel is the
    only reason this memory is found at all.
    """
    service, sessions = make_service(repository, database_engine)
    seed(
        repository, sessions, "mem_kw",
        "sqlite-vec exposes an ANN extension for brute-force alternatives.",
        [0.0, 1.0, 0.0],  # orthogonal to QUERY_VEC: below the similarity floor
    )

    result = service.retrieve("sqlite-vec")

    assert [e.memory_id for e in result.evidence] == ["mem_kw"]
    assert result.evidence[0].similarity == 0.0  # not a cosine score
    assert result.evidence[0].keyword_rank == 1
    assert result.evidence[0].matched_by == (KEYWORD_CHANNEL,)


def test_semantic_only_match_is_returned_when_keywords_find_nothing(
    repository, database_engine
):
    """A paraphrase with no shared tokens is exactly what embeddings are for."""
    service, sessions = make_service(repository, database_engine)
    seed(
        repository, sessions, "mem_sem",
        "Dense numerical representations capture conceptual closeness.",
        RAG_VEC,
    )

    result = service.retrieve("How do I store vectors?")

    assert [e.memory_id for e in result.evidence] == ["mem_sem"]
    assert result.evidence[0].keyword_rank is None
    assert result.evidence[0].similarity > 0


def test_empty_corpus_returns_empty_evidence_not_an_error(repository, database_engine):
    service, _ = make_service(repository, database_engine)
    result = service.retrieve("What did I learn about RAG?")
    assert result.evidence == []
    assert result.candidates_considered == 0
    assert set(result.channels) == {SEMANTIC_CHANNEL, KEYWORD_CHANNEL}


def test_irrelevant_question_returns_no_evidence(repository, database_engine):
    service, sessions = make_service(repository, database_engine)
    seed(repository, sessions, "mem_cook", "Pasta needs salted boiling water.", COOK_VEC)

    result = service.retrieve("zzzzz qqqqq")

    assert result.evidence == []


def test_deleted_memories_never_appear_in_hybrid_results(repository, database_engine):
    service, sessions = make_service(repository, database_engine)
    seed(
        repository, sessions, "mem_gone",
        "HNSW graphs index embeddings for similarity search.",
        RAG_VEC, title="HNSW embeddings",
    )
    assert repository.delete_by_id("mem_gone") is True

    result = service.retrieve("How do HNSW graphs index embeddings?")

    assert result.evidence == []
    assert result.candidates_considered == 0


def test_temporal_expression_filters_both_channels(repository, database_engine):
    """The same window applies to keyword and semantic candidates alike."""
    service, sessions = make_service(repository, database_engine)
    seed(
        repository, sessions, "mem_old",
        "HNSW graphs index embeddings for similarity search.",
        RAG_VEC, captured_at=NOW - timedelta(days=60),
        title="HNSW embeddings",
    )

    result = service.retrieve("How do HNSW graphs index embeddings last week?")

    assert result.evidence == []
    assert result.temporal is not None
    assert result.temporal.expression == "last week"


def test_explicit_date_filter_wins_over_the_parsed_expression(repository, database_engine):
    """An explicit caller range overrides "last week"; both channels obey it."""
    service, sessions = make_service(repository, database_engine)
    seed(
        repository, sessions, "mem_sept",
        "HNSW graphs index embeddings for similarity search.",
        RAG_VEC, captured_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
        title="HNSW embeddings",
    )
    seed(
        repository, sessions, "mem_last_week",
        "HNSW graphs index embeddings for similarity search.",
        RAG_VEC, captured_at=NOW - timedelta(days=3),
        title="HNSW embeddings",
    )

    # Question says "last week" (Oct 5-11) but the caller asks for September.
    result = service.retrieve(
        "How do HNSW graphs index embeddings last week?",
        from_date=date(2026, 9, 1),
        to_date=date(2026, 9, 30),
    )

    assert [e.memory_id for e in result.evidence] == ["mem_sept"]
    # The parsed expression is still reported for transparency.
    assert result.temporal is not None
    assert result.temporal.expression == "last week"


def test_explicit_date_filter_applies_to_keyword_only_results(repository, database_engine):
    """The keyword channel gets the same window as the semantic one."""
    service, sessions = make_service(repository, database_engine)
    seed(
        repository, sessions, "mem_old_kw",
        "Notes about sqlite-vec and vector search.",
        RAG_VEC, captured_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )

    result = service.retrieve(
        "sqlite-vec",
        from_date=date(2026, 10, 1),
        to_date=date(2026, 10, 11),
    )

    assert result.evidence == []


def test_inverted_explicit_date_range_raises_input_error(repository, database_engine):
    service, _sessions = make_service(repository, database_engine)
    with pytest.raises(RetrievalInputError):
        service.retrieve(
            "HNSW embeddings",
            from_date=date(2026, 10, 11),
            to_date=date(2026, 10, 1),
        )


def test_top_k_limits_the_returned_evidence(repository, database_engine):
    service, sessions = make_service(repository, database_engine)
    for n in range(4):
        seed(
            repository, sessions, f"mem_{n}",
            f"HNSW graphs index embeddings variant number {n}.",
            RAG_VEC, title=f"HNSW embeddings {n}",
        )

    result = service.retrieve("HNSW embeddings", top_k=2)

    assert len(result.evidence) == 2
    scores = [e.score for e in result.evidence]
    assert scores == sorted(scores, reverse=True)


def test_same_query_twice_returns_an_identical_ranking(repository, database_engine):
    service, sessions = make_service(repository, database_engine)
    for n in range(3):
        seed(
            repository, sessions, f"mem_{n}",
            f"HNSW graphs index embeddings variant number {n}.",
            RAG_VEC, title=f"HNSW embeddings {n}",
        )

    first = [(e.chunk_id, e.score) for e in service.retrieve("HNSW embeddings").evidence]
    second = [(e.chunk_id, e.score) for e in service.retrieve("HNSW embeddings").evidence]
    assert first == second


def test_evidence_carries_real_stored_metadata(repository, database_engine):
    """Citations must trace to stored rows, never invented metadata."""
    service, sessions = make_service(repository, database_engine)
    seed(
        repository, sessions, "mem_meta",
        "HNSW graphs index embeddings for similarity search.",
        RAG_VEC, title="HNSW embeddings",
        source_type="browser",
        source_url="https://example.com/hnsw",
        domain="example.com",
    )

    item = service.retrieve("How do HNSW graphs index embeddings?").evidence[0]

    assert item.source_type == "browser"
    assert item.source_title == "HNSW embeddings"
    assert item.source_url == "https://example.com/hnsw"
    assert item.domain == "example.com"
    assert item.captured_at is not None
    assert item.chunk_id.startswith("chk_")
    assert item.memory_id == "mem_meta"
    assert item.source_id is not None


# --- Channel failure handling ---------------------------------------------


def test_embedding_outage_falls_back_to_keyword_results(repository, database_engine):
    """A dead embedding model must not blank out an answerable question."""
    service, sessions = make_service(repository, database_engine, failing=True)
    seed(
        repository, sessions, "mem_kw",
        "sqlite-vec exposes an ANN extension for brute-force alternatives.",
        RAG_VEC, title="sqlite-vec",
    )

    result = service.retrieve("sqlite-vec")

    assert [e.memory_id for e in result.evidence] == ["mem_kw"]
    assert result.channels == (KEYWORD_CHANNEL,)


def test_embedding_outage_with_no_keyword_weight_is_unavailable(repository, database_engine):
    service, sessions = make_service(
        repository, database_engine, failing=True, rag_keyword_weight=0.0
    )
    seed(repository, sessions, "mem_a", "HNSW graphs index embeddings.", RAG_VEC)

    with pytest.raises(RetrievalUnavailableError):
        service.retrieve("How do HNSW graphs index embeddings?")


def test_keyword_index_failure_falls_back_to_semantic_results(repository, database_engine):
    service, sessions = make_service(repository, database_engine)
    seed(repository, sessions, "mem_sem", "Dense vectors capture conceptual closeness.", RAG_VEC)

    class _BrokenKeywords:
        def search(self, *_a, **_k):
            raise StorageError("simulated keyword index failure")

    service._keywords = _BrokenKeywords()

    result = service.retrieve("How do I store vectors?")

    assert [e.memory_id for e in result.evidence] == ["mem_sem"]
    assert result.channels == (SEMANTIC_CHANNEL,)


def test_both_channels_failing_is_unavailable(repository, database_engine):
    service, sessions = make_service(repository, database_engine, failing=True)
    seed(repository, sessions, "mem_a", "HNSW graphs index embeddings.", RAG_VEC)

    class _BrokenKeywords:
        def search(self, *_a, **_k):
            raise StorageError("simulated keyword index failure")

    service._keywords = _BrokenKeywords()

    with pytest.raises(RetrievalUnavailableError):
        service.retrieve("How do HNSW graphs index embeddings?")


# --- Query validation ------------------------------------------------------


@pytest.mark.parametrize("question", ["", "   ", None, 123])
def test_invalid_questions_raise_input_error(repository, database_engine, question):
    service, _ = make_service(repository, database_engine)
    with pytest.raises(RetrievalInputError):
        service.retrieve(question)


def test_oversized_question_raises_input_error(repository, database_engine):
    service, _ = make_service(repository, database_engine)
    with pytest.raises(RetrievalInputError):
        service.retrieve("x" * 5000)




