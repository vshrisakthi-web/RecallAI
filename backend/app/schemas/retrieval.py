"""Request and response models for the retrieval (Ask RecallAI) endpoint.

Retrieval returns **evidence, not answers**. No model generates prose here, so
the response deliberately has no ``answer`` field: inventing one would let the
UI present a guess as a confident reply. Every evidence item carries the ids and
metadata needed to trace it back to a real stored record.
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    """One retrieval request from the Ask RecallAI surface.

    Only the question and optional paging/filters are accepted. There is no
    ``api_key`` field and no way to pass credentials: the local model needs
    none, so accepting one would only create a place to leak it.

    ``from_date``/``to_date`` are inclusive UTC calendar days, the same
    day-granular convention as the memories list API; an explicit range wins
    over a window parsed from the question text. Both are optional.
    """

    question: str = Field(min_length=1, max_length=1000)
    top_k: Optional[int] = Field(default=None, ge=1, le=20)
    from_date: Optional[date] = None
    to_date: Optional[date] = None


class EvidenceItem(BaseModel):
    """One grounded passage, traceable to the record it came from.

    ``similarity`` is a cosine score in [-1, 1], or 0.0 when the passage was
    matched by keywords only (BM25 and cosine are not comparable). ``score`` is
    the fused reciprocal-rank-fusion score used to order results. Callers should
    use ``confidence`` for display, never ``score``, which is only meaningful
    for comparison within one response.
    """

    chunk_id: str
    memory_id: str
    source_id: Optional[str] = None
    source_type: Optional[str] = None
    source_title: Optional[str] = None
    source_url: Optional[str] = None
    domain: Optional[str] = None
    captured_at: Optional[datetime] = None
    passage: str
    similarity: float
    keyword_rank: Optional[int] = None
    score: float = 0.0
    matched_by: list[str] = Field(default_factory=list)
    confidence: str = "none"


class AskResponse(BaseModel):
    """The result of one retrieval call.

    Fields:
        question: the question exactly as received (never rewritten), so the UI
            can echo what was actually searched.
        evidence: ranked passages, highest-ranked first. May be empty.
        confidence: overall retrieval strength — "none", "weak", or "strong".
            Reported so the UI can tell the user how much to trust the evidence
            instead of implying certainty that is not there.
        channels: which retrieval channels contributed.
        candidates_considered: how many raw candidates were examined, so a low
            result count can be explained rather than guessed at.
        temporal: the window parsed from the question, when one was recognized.
        request_id: correlation id echoed from the request-ID middleware.
    """

    question: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    confidence: str = "none"
    channels: list[str] = Field(default_factory=list)
    candidates_considered: int = 0
    temporal_expression: Optional[str] = None
    temporal_from: Optional[datetime] = None
    temporal_to: Optional[datetime] = None
    request_id: Optional[str] = None
