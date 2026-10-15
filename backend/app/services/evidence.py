"""Shared retrieval types and evidence assembly (Module 6, Tasks 6.4–6.6).

Plain English: this module holds what semantic retrieval (6.4) and hybrid
retrieval (6.5) share — the question validation/temporal parsing
re-exported from ``temporal.py``, the grounded ``Evidence`` record, and the
join that turns a chunk id into evidence from real database rows.

The assembly join is the deletion guarantee: it requires the chunk row AND
the memory row to exist. A hit whose chunk or memory is gone returns None
and is skipped — never fabricated, never surfaced.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from typing import Optional

from app.repositories.base import StorageError
from app.repositories.chunk_store import ChunkRepository
from app.repositories.sqlite_store import MemoryRepository
from app.services.temporal import (
    NormalizedQuery,
    QueryInputError,
    TemporalFilter,
    normalize_and_parse,
)

__all__ = [
    "Evidence",
    "FusedCandidate",
    "RetrievalInputError",
    "RetrievalResult",
    "RetrievalUnavailableError",
    "assemble_evidence",
    "effective_window",
    "fuse_rankings",
    "in_window",
    "normalize_and_parse",
    "NormalizedQuery",
    "QueryInputError",
    "TemporalFilter",
]

SEMANTIC_CHANNEL = "semantic"
KEYWORD_CHANNEL = "keyword"


class RetrievalInputError(ValueError):
    """Raised for empty/oversized questions and invalid date filters."""


class RetrievalUnavailableError(RuntimeError):
    """Raised when the embedding model or vector index cannot serve a query."""


@dataclass(frozen=True)
class Evidence:
    """One grounded evidence passage. Every field comes from stored rows.

    Attributes:
        chunk_id / memory_id / source_id: stable ids that trace this passage
            back to real stored records. Never fabricated.
        passage: the chunk's stored text, verbatim.
        similarity: cosine similarity of the semantic channel, or 0.0 when the
            passage was found only by the keyword channel (keyword scores are
            BM25 and live on an incompatible scale, so they are never reported
            here as if they were cosine values).
        keyword_rank: 1-based keyword rank when the keyword channel matched.
        score: the fused ranking score actually used to order results. Present
            so ranking is inspectable rather than implicit.
        matched_by: which channels surfaced this passage, in deterministic order
            ("semantic", "keyword", or both). Lets callers distinguish a true
            hybrid hit from a single-channel one.
    """

    chunk_id: str
    memory_id: str
    passage: str
    source_id: Optional[str]
    source_type: Optional[str]
    source_title: Optional[str]
    source_url: Optional[str]
    domain: Optional[str]
    captured_at: Optional[datetime]
    similarity: float
    keyword_rank: Optional[int] = None  # 1-based FTS rank, when applicable
    score: float = 0.0  # fused RRF score used for ordering
    matched_by: tuple[str, ...] = ("semantic",)


@dataclass(frozen=True)
class RetrievalResult:
    """The full answer to one retrieval call (before any LLM is involved)."""

    query: NormalizedQuery

def effective_window(
    from_date: Optional[date],
    to_date: Optional[date],
    temporal: Optional[TemporalFilter],
) -> tuple[Optional[date], Optional[date]]:
    """Merge caller dates with the parsed expression.

    An explicit caller filter wins; the parsed expression is still reported
    on the result for transparency. Bounds are inclusive on both ends.
    """
    if from_date is not None and to_date is not None and from_date > to_date:
        raise RetrievalInputError("from_date must not be after to_date.")
    start = from_date if from_date is not None else (
        temporal.from_date if temporal else None
    )
    end = to_date if to_date is not None else (
        temporal.to_date if temporal else None
    )
    return start, end


def in_window(
    captured: Optional[datetime],
    from_date: Optional[date],
    to_date: Optional[date],
) -> bool:
    """Check one memory's event time against the inclusive date window."""
    if from_date is None and to_date is None:
        return True
    if captured is None:
        return False  # no event time: cannot claim it fits the window
    day = captured.astimezone(timezone.utc).date()
    if from_date is not None and day < from_date:
        return False
    if to_date is not None and day > to_date:
        return False
    return True


def assemble_evidence(
    chunk_id: str,
    memory_id: str,
    similarity: float,
    chunks: ChunkRepository,
    memories: MemoryRepository,
    keyword_rank: Optional[int] = None,
) -> Optional[Evidence]:
    """Join one retrieval hit to its chunk, memory, and source rows.

    Returns None when the chunk or memory row is gone (deleted memories are
    excluded here, at the retrieval layer, not in the UI).
    """
    try:
        chunk = chunks.get_by_id(chunk_id)
    except StorageError:
        return None
    if chunk is None or chunk.memory_id != memory_id:
        return None
    try:
        record = memories.get_by_id(memory_id)
    except StorageError:
        return None
    if record is None:
        return None  # deleted memory — excluded at the retrieval layer
    source_type = record.source_type
    if hasattr(source_type, "value"):
        source_type = source_type.value
    return Evidence(
        chunk_id=chunk.id,
        memory_id=memory_id,
        passage=chunk.chunk_text,
        source_id=chunk.source_id,
        source_type=str(source_type) if source_type is not None else None,
        source_title=record.title or None,
        source_url=record.source_url,
        domain=record.domain,
        captured_at=record.captured_at,
        similarity=similarity,
        keyword_rank=keyword_rank,
    )


@dataclass(frozen=True)
class FusedCandidate:
    """One deduplicated candidate ranked by reciprocal rank fusion.

    Plain English: each channel hands us an ordered list ("this chunk was my
    1st best guess, that one my 2nd..."). We merge those lists by chunk id, so a
    chunk found by *both* channels gets credit from both. The chunk keeps its
    cosine similarity and its keyword rank so the evidence stays inspectable.

    Why RRF instead of averaging scores: BM25 and cosine similarity live on
    completely different scales (BM25 is unbounded, cosine is [-1, 1]), so
    averaging them is meaningless. RRF only uses *rank position*, which both
    channels can express, with the formula:

        score(chunk) = weight / (k + rank)

    ``k`` (default 60) dampens how much the very top result dominates. With
    equal weights, a chunk ranked 1st by both channels outscores a chunk ranked
    1st by one and 5th by the other, which is the behaviour we want.
    """

    chunk_id: str
    memory_id: str
    score: float
    similarity: float
    keyword_rank: Optional[int]
    matched_by: tuple[str, ...]


def fuse_rankings(
    semantic: list[tuple[str, str, float]],
    keyword: list[tuple[str, str, int]],
    semantic_weight: float = 1.0,
    keyword_weight: float = 1.0,
    rrf_k: int = 60,
) -> list[FusedCandidate]:
    """Merge semantic and keyword rankings with weighted reciprocal rank fusion.

    Arguments:
        semantic: ``(chunk_id, memory_id, similarity)`` in cosine-descending
            order. Position 1 is the best match.
        keyword: ``(chunk_id, memory_id, rank)`` in BM25/LIKE order, where
            ``rank`` is already 1-based.
        semantic_weight / keyword_weight: per-channel multipliers. Equal by
            default so neither channel dominates. A weight of 0 disables that
            channel's contribution while keeping its results inspectable.
        rrf_k: the RRF smoothing constant. Larger values flatten the ranking.

    Returns:
        Candidates sorted by fused score descending, then by chunk id
        ascending. Sorting on chunk id as the tie-break makes the order fully
        deterministic: identical inputs always produce an identical ranking.

    Determinism and dedup: a chunk appearing in both lists is merged into one
    candidate (never duplicated), and a chunk repeated within a single channel
    is counted once per channel at its best (lowest) rank.
    """
    if rrf_k < 1:
        raise ValueError("rrf_k must be at least 1")

    scores: dict[str, float] = {}
    similarity: dict[str, float] = {}
    keyword_rank: dict[str, int] = {}
    memory_ids: dict[str, str] = {}
    channels: dict[str, list[str]] = {}

    # --- Semantic channel: position in the list IS the rank (1-based) -------
    for position, (chunk_id, memory_id, score) in enumerate(semantic, start=1):
        if semantic_weight <= 0:
            continue
        scores[chunk_id] = scores.get(chunk_id, 0.0) + semantic_weight / (rrf_k + position)
        # Keep the best (highest) similarity if a chunk somehow repeats.
        similarity[chunk_id] = max(similarity.get(chunk_id, score), score)
        memory_ids[chunk_id] = memory_id
        seen = channels.setdefault(chunk_id, [])
        if SEMANTIC_CHANNEL not in seen:
            seen.append(SEMANTIC_CHANNEL)

    # --- Keyword channel: collapse to each chunk's best (lowest) rank -------
    best_keyword_rank: dict[str, int] = {}
    for chunk_id, memory_id, rank in keyword:
        best = best_keyword_rank.get(chunk_id)
        if best is None or rank < best:
            best_keyword_rank[chunk_id] = rank
            memory_ids.setdefault(chunk_id, memory_id)

    for chunk_id, rank in best_keyword_rank.items():
        if keyword_weight <= 0:
            continue
        scores[chunk_id] = scores.get(chunk_id, 0.0) + keyword_weight / (rrf_k + rank)
        keyword_rank[chunk_id] = rank
        memory_ids.setdefault(chunk_id, "")
        seen = channels.setdefault(chunk_id, [])
        if KEYWORD_CHANNEL not in seen:
            seen.append(KEYWORD_CHANNEL)

    # Score descending, then chunk id ascending: a total, stable ordering.
    # Python's sort is stable, so without the explicit id tie-break two chunks
    # with the same fused score would keep their insertion order — which depends
    # on which channel was processed first. The id tie-break removes that.
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [
        FusedCandidate(
            chunk_id=chunk_id,
            memory_id=memory_ids.get(chunk_id, ""),
            score=score,
            similarity=similarity.get(chunk_id, 0.0),
            keyword_rank=keyword_rank.get(chunk_id),
            # Canonical channel order regardless of which channel was seen first.
            matched_by=tuple(
                name
                for name in (SEMANTIC_CHANNEL, KEYWORD_CHANNEL)
                if name in channels.get(chunk_id, [])
            ),
        )
        for chunk_id, score in ordered
    ]


@dataclass(frozen=True)
class RetrievalResult:
    """The full answer to one retrieval call (before any LLM is involved).

    Attributes:
        query: the validated question plus any parsed temporal filter.
        evidence: ranked, grounded passages. Every field comes from stored rows.
        candidates_considered: how many raw candidates each channel produced.
        temporal: the window parsed from the question, when one was recognized.
        channels: which retrieval channels actually contributed, in
            deterministic order. Reported so callers can tell a genuine
            semantic-only result from a keyword channel that silently failed.
    """

    query: NormalizedQuery
    evidence: list[Evidence]
    candidates_considered: int
    temporal: Optional[TemporalFilter]
    channels: tuple[str, ...] = ("semantic",)
