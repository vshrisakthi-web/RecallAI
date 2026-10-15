"""Task 6.4 — semantic retrieval service tests.

Fully offline: the embedding service uses a fake transport with fixed
vectors, and "now" is injected. Covers ranking, evidence grounding, temporal
filtering from text and from caller args, deleted-memory exclusion, empty
results, and embedding/index failure mapping.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.repositories.chunk_store import ChunkRepository
from app.repositories.vector_store import VectorStore
from app.services.chunking import chunk_text
from app.services.embeddings import EmbeddingService
from app.services.retrieval import (
    RetrievalInputError,
    RetrievalUnavailableError,
    SemanticRetrievalService,
)
from tests._factories import make_record, utcnow

NOW = datetime(2026, 10, 12, 12, 0, 0, tzinfo=timezone.utc)

# Fixed 3-dim vectors: "RAG-like" ~= [1,0,0], "cooking-like" ~= [0,1,0].
RAG_VEC = [1.0, 0.05, 0.0]

def make_embeddings(vector, model="unit-embed-model"):
    """Fake-transport embedding service returning a fixed query vector."""

    def fake_post(url: str, **kwargs):
        inputs = kwargs["json"]["input"]
        return httpx.Response(
            200,
            json={"embeddings": [list(vector) for _ in inputs]},
            request=httpx.Request("POST", url),
        )

    config = Settings(
        ollama_base_url="http://127.0.0.1:11434", embedding_model=model
    )
    return EmbeddingService(config=config, post=fake_post), config


def make_service(repository, database_engine, vector=None, model="unit-embed-model"):
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    embeddings, _ = make_embeddings(vector or QUERY_VEC, model)
    return SemanticRetrievalService(
        memories=repository,
        chunks=ChunkRepository(sessions),
        vectors=VectorStore(sessions),
        embeddings=embeddings,
        now=lambda: NOW,
    ), sessions


def seed(repository, sessions, memory_id, text, vector, captured_at=None, **kwargs):
    """Save a memory, chunk it, and store a fixed vector for each chunk."""
    record = make_record(
        id=memory_id,
        _text=text,
        captured_at=captured_at or utcnow(),
        **kwargs,
    )
    saved, _ = repository.save_or_get(record)
    chunk_ids = ChunkRepository(sessions).replace_memory_chunks(
        saved.id, chunk_text(saved.normalized_text, saved.id)
    )
    VectorStore(sessions).upsert_many(
        [(cid, saved.id, list(vector)) for cid in chunk_ids], "unit-embed-model"
    )
    return saved, chunk_ids


# --- Ranking and evidence ----------------------------------------------------


def test_ranked_results_carry_grounded_metadata(repository, database_engine):
    service, sessions = make_service(repository, database_engine)
    seed(
        repository, sessions, "mem_rag", "Retrieval augmented generation grounds answers.",
        RAG_VEC,
        source_type="browser",
        title="RAG notes",
        source_url="https://example.com/rag",
        domain="example.com",
    )
    seed(repository, sessions, "mem_cook", "Pasta needs salted boiling water.", COOK_VEC)

    result = service.retrieve("What did I learn about RAG?")

    # The cooking chunk scores below the similarity floor, so only the RAG
    # chunk survives: weak evidence is filtered, not ranked last.
    assert result.candidates_considered == 1
    assert len(result.evidence) == 1
    top = result.evidence[0]
    assert top.memory_id == "mem_rag"
    assert "Retrieval augmented generation" in top.passage
    assert top.source_type == "browser"
    assert top.source_title == "RAG notes"
    assert top.source_url == "https://example.com/rag"
    assert top.domain == "example.com"
    assert top.captured_at is not None


def test_scores_descend_in_rank_order(repository, database_engine):
    service, sessions = make_service(repository, database_engine)
    # Three RAG-flavored chunks with graded similarity to the query vector.
    # Texts differ so each seed stores a distinct memory (dedup key).
    seed(repository, sessions, "mem_best", "RAG retrieval ranking best note.", [0.95, 0.1, 0.0])
    seed(repository, sessions, "mem_mid", "RAG retrieval ranking middle note.", [0.8, 0.3, 0.0])
    seed(repository, sessions, "mem_low", "RAG retrieval ranking lower note.", [0.6, 0.4, 0.0])

    result = service.retrieve("What did I learn about RAG?")

    assert [e.memory_id for e in result.evidence] == ["mem_best", "mem_mid", "mem_low"]
    scores = [e.similarity for e in result.evidence]
    assert scores == sorted(scores, reverse=True)


def test_question_text_reaches_embedder_unmodified(repository, database_engine):
    seen: list = []

    def fake_post(url: str, **kwargs):
        seen.append(kwargs["json"]["input"])
        return httpx.Response(
            200,
            json={"embeddings": [list(QUERY_VEC)]},
            request=httpx.Request("POST", url),
        )

    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    embeddings = EmbeddingService(
        config=Settings(
            ollama_base_url="http://127.0.0.1:11434",
            embedding_model="unit-embed-model",
        ),
        post=fake_post,
    )
    service = SemanticRetrievalService(
        memories=repository,
        chunks=ChunkRepository(sessions),
        vectors=VectorStore(sessions),
        embeddings=embeddings,
        now=lambda: NOW,
    )
    service.retrieve("  What is RAG?  ")
    assert seen == [["What is RAG?"]]


# --- Validation ---------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "   ", None, 42])
def test_invalid_questions_rejected(repository, database_engine, bad):
    service, _ = make_service(repository, database_engine)
    with pytest.raises(RetrievalInputError):
        service.retrieve(bad)  # type: ignore[arg-type]


def test_oversized_question_rejected(repository, database_engine):
    service, _ = make_service(repository, database_engine)
    with pytest.raises(RetrievalInputError):
        service.retrieve("x" * 5000)


def test_inverted_date_range_rejected(repository, database_engine):
    service, _ = make_service(repository, database_engine)
    with pytest.raises(RetrievalInputError):
        service.retrieve(
            "notes", from_date=date(2026, 10, 10), to_date=date(2026, 10, 1)
        )


def test_empty_index_returns_empty_evidence(repository, database_engine):
    service, _ = make_service(repository, database_engine)
    result = service.retrieve("What did I learn about RAG?")
    assert result.evidence == []
    assert result.candidates_considered == 0

COOK_VEC = [0.05, 1.0, 0.0]

# --- Temporal filtering -------------------------------------------------------


def test_last_week_filter_from_question_text(repository, database_engine):
    service, sessions = make_service(repository, database_engine)
    in_week = NOW - timedelta(days=3)  # 2026-10-09, inside last week
    old = NOW - timedelta(days=30)  # September, outside last week
    seed(repository, sessions, "mem_fresh", "RAG uses cosine similarity search.", RAG_VEC, captured_at=in_week)
    seed(repository, sessions, "mem_old", "RAG uses cosine similarity search.", RAG_VEC, captured_at=old)

    result = service.retrieve("What did I learn about RAG last week?")

    assert result.temporal is not None
    assert result.temporal.expression == "last week"
    assert [e.memory_id for e in result.evidence] == ["mem_fresh"]


def test_explicit_caller_dates_win_over_question_text(repository, database_engine):
    service, sessions = make_service(repository, database_engine)
    sept = datetime(2026, 9, 15, tzinfo=timezone.utc)
    seed(repository, sessions, "mem_sept", "RAG uses cosine similarity search.", RAG_VEC, captured_at=sept)

    result = service.retrieve(
        "What did I learn about RAG last week?",
        from_date=date(2026, 9, 1),
        to_date=date(2026, 9, 30),
    )

    # Caller window (September) overrides the parsed "last week".
    assert [e.memory_id for e in result.evidence] == ["mem_sept"]
    # ...but the parsed expression is still reported for transparency.
    assert result.temporal is not None and result.temporal.expression == "last week"


def test_date_boundaries_are_inclusive(repository, database_engine):
    service, sessions = make_service(repository, database_engine)
    monday = datetime(2026, 10, 5, 0, 0, 0, tzinfo=timezone.utc)
    sunday = datetime(2026, 10, 11, 23, 59, 59, tzinfo=timezone.utc)
    # Distinct texts: identical text would dedup into one memory.
    seed(repository, sessions, "mem_mon", "RAG notes from Monday morning.", RAG_VEC, captured_at=monday)
    seed(repository, sessions, "mem_sun", "RAG notes from Sunday evening.", RAG_VEC, captured_at=sunday)

    result = service.retrieve("What did I learn about RAG last week?")

    assert sorted(e.memory_id for e in result.evidence) == ["mem_mon", "mem_sun"]


def test_no_matching_dates_yields_empty(repository, database_engine):
    service, sessions = make_service(repository, database_engine)
    seed(
        repository, sessions, "mem_old2", "RAG uses cosine similarity search.",
        RAG_VEC, captured_at=NOW - timedelta(days=60),
    )
    result = service.retrieve("What did I learn about RAG last week?")
    assert result.evidence == []
    assert result.candidates_considered == 1  # found, then filtered by date


# --- Deleted memories ----------------------------------------------------------


def test_deleted_memories_never_appear(repository, database_engine):
    service, sessions = make_service(repository, database_engine)
    seed(repository, sessions, "mem_gone", "RAG uses cosine similarity search.", RAG_VEC)
    assert repository.delete_by_id("mem_gone") is True

    result = service.retrieve("What did I learn about RAG?")

    assert result.evidence == []
    assert result.candidates_considered == 0  # vectors cascaded away too


def test_assemble_skips_missing_chunk_or_memory(repository, database_engine):
    # Defense in depth: FK cascades normally prevent orphan vectors, so the
    # skip logic is exercised directly — a hit with no chunk or no memory
    # row must yield None, never fabricated evidence.
    service, sessions = make_service(repository, database_engine)
    assert service._assemble("chk_missing", "mem_missing", 0.9) is None

    saved, chunk_ids = seed(
        repository, sessions, "mem_half", "RAG uses cosine similarity search.", RAG_VEC
    )
    ChunkRepository(sessions).delete_memory_chunks(saved.id)
    # Chunk row gone while the memory lives on: assembly skips the hit.
    assert service._assemble(chunk_ids[0], saved.id, 0.9) is None


# --- Failure mapping ------------------------------------------------------------


def test_embedding_outage_maps_to_unavailable(repository, database_engine):
    def failing_post(url: str, **kwargs):
        raise httpx.ConnectError("refused", request=httpx.Request("POST", url))

    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    embeddings = EmbeddingService(
        config=Settings(
            ollama_base_url="http://127.0.0.1:11434",
            embedding_model="unit-embed-model",
        ),
        post=failing_post,
    )
    service = SemanticRetrievalService(
        memories=repository,
        chunks=ChunkRepository(sessions),
        vectors=VectorStore(sessions),
        embeddings=embeddings,
        now=lambda: NOW,
    )
    with pytest.raises(RetrievalUnavailableError):
        service.retrieve("What did I learn about RAG?")


def test_stale_model_generation_searches_nothing(repository, database_engine):
    # Vectors indexed under a different model are invisible to this service.
    service, sessions = make_service(
        repository, database_engine, model="new-model"
    )
    seed(repository, sessions, "mem_stale", "RAG uses cosine similarity search.", RAG_VEC)
    result = service.retrieve("What did I learn about RAG?")
    assert result.evidence == []
    assert result.candidates_considered == 0


def test_similarity_floor_filters_weak_hits(repository, database_engine):
    service, sessions = make_service(repository, database_engine)
    # Cooking vector is nearly orthogonal to the RAG query vector.
    seed(repository, sessions, "mem_weak", "Pasta needs salted boiling water.", COOK_VEC)
    result = service.retrieve("Explain retrieval augmented generation.")
    assert result.evidence == []

QUERY_VEC = [0.95, 0.1, 0.0]
