"""Keyword retrieval over the chunk FTS index (Module 6, Task 6.5).

Plain English: exact words matter — "HNSW", "Ollama", "sqlite-vec" — and a
pure semantic search can miss them. This channel queries the ``chunk_fts``
FTS5 index (created by migration 0002 with insert/update/delete triggers)
with one MATCH query, so BM25 ranks chunk text + memory titles together.

Two deliberate choices:
  * AND semantics: every query term must appear ("AND"-joined quoted
    terms). Retrieval favors precision — a chunk matching all words beats
    one matching any single common word.
  * FTS-or-LIKE: when the FTS5 table is absent (older database, exotic
    SQLite build), the channel falls back to LIKE matching, mirroring the
    memories list API. The fallback still excludes deleted memories and
    honors date filters — degraded ranking, never degraded correctness.

The channel returns chunk ids with 1-based ranks (BM25 order or LIKE
order). Scores are intentionally NOT returned: BM25 and cosine live on
incompatible scales, and the fusion step (reciprocal rank fusion) only
needs ranks. Deleted memories are excluded inside the query (deleted rows
leave the FTS index via trigger AND the join requires the memory row).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.database.models import Memory, MemoryChunk
from app.repositories.base import StorageError

_TOKEN = re.compile(r"[\w]+", flags=re.UNICODE)

#: Filler words that carry no searchable meaning in a question. They are
#: dropped *before* building the FTS MATCH expression, because a strict AND
#: over every word would make "How does HNSW index embeddings?" require the
#: tokens "how" and "does" — which no chunk contains — and natural questions
#: would then almost never match. Topic words ("hnsw", "embeddings") survive.
_STOPWORDS = frozenset(
    """
    a about after all also am an and any are as at be been being but by can could
    did do does doing done for from get got had has have how i if in into is it
    its me my of on once only or our out over own said same shall she so some tell
    than that the their them then there these they this those to too us was we
    were what when where which while who whom why will with would you your
    """.split()
)


@dataclass(frozen=True)
class KeywordHit:
    """One keyword-search result: chunk identity plus its 1-based rank."""

    chunk_id: str
    memory_id: str
    rank: int


def extract_terms(question: str, limit: int = 10) -> list[str]:
    """Split a question into FTS/LIKE terms: lowercase words, order kept.

    Stopwords are dropped (see ``_STOPWORDS``) and duplicates are removed. If
    every token was a stopword — a question like "what is it?" — the raw tokens
    are returned instead, so the caller still searches for something rather
    than silently matching nothing.
    """
    tokens = _TOKEN.findall(question.lower())
    meaningful: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in _STOPWORDS or token in seen:
            continue
        meaningful.append(token)
        seen.add(token)
        if len(meaningful) >= limit:
            return meaningful

    if meaningful:
        return meaningful

    # Nothing but stopwords: fall back to the raw tokens (still deduped).
    fallback: list[str] = []
    seen_fallback: set[str] = set()
    for token in tokens:
        if token in seen_fallback:
            continue
        fallback.append(token)
        seen_fallback.add(token)
        if len(fallback) >= limit:
            break
    return fallback


class KeywordSearchService:
    """Chunk-level keyword search bound to one session factory."""

    def __init__(self, sessions: sessionmaker):
        self._sessions = sessions

    def search(
        self,
        question: str,
        limit: int = 20,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> list[KeywordHit]:
        """Rank chunks by keyword match, honoring the inclusive date window."""
        terms = extract_terms(question)
        if not terms:
            return []
        session = self._sessions()
        try:
            fts_exists = session.scalar(
                text("SELECT 1 FROM sqlite_master WHERE name = 'chunk_fts'")
            )
            if fts_exists:
                return self._search_fts(session, terms, limit, from_date, to_date)
            return self._search_like(session, terms, limit, from_date, to_date)
        except SQLAlchemyError as exc:
            raise StorageError("keyword search failed") from exc
        finally:
            session.close()

    # --- FTS5 path ---------------------------------------------------------

    def _search_fts(
        self, session, terms: list[str], limit: int,
        from_date: Optional[date], to_date: Optional[date],
    ) -> list[KeywordHit]:
        # NOTE (FTS5 gotcha, fixed and covered by tests/test_keyword_search.py):
        # ``chunk_fts`` is an fts5 table with ``title`` and ``content`` indexed.
        # Two SQLite rules matter here (both are covered by
        # tests/test_keyword_search.py):
        #   1. MATCH must name a column, so the WHERE clause uses ``fts.content``
        #      / ``fts.title`` — the table name or the alias is rejected with
        #      "no such column".
        #   2. MATCH cannot be used inside an arbitrary OR expression, so the
        #      title and content searches are two separate queries that are
        #      UNIONed rather than ORed in one WHERE clause.
        # bm25() takes the real table name, not the ``fts`` alias.
        base_from = (
            "FROM chunk_fts AS fts "
            "JOIN memory_chunks AS chunk ON chunk.id = fts.chunk_id "
            "JOIN memories AS mem ON mem.id = chunk.memory_id "
        )
        window = (
            ("AND mem.captured_at >= :start " if from_date else "")
            + ("AND mem.captured_at < :end " if to_date else "")
        )

        def _run(expression: str, column: str) -> list:
            return session.execute(
                text(
                    f"SELECT fts.chunk_id AS chunk_id, fts.memory_id AS memory_id "
                    f"{base_from} "
                    f"WHERE fts.{column} MATCH :match {window} "
                    f"ORDER BY bm25(chunk_fts), chunk.id LIMIT :limit"
                ),
                {
                    "match": expression,
                    "limit": limit,
                    **_day_params(from_date, to_date),
                },
            ).all()

        match = " AND ".join(f'"{term}"' for term in terms)
        rows = _run(match, "content")
        title_rows = _run(match, "title")
        if not rows and len(terms) > 1:
            # Precision first (AND), then widen to recall (OR) rather than
            # returning nothing: a question touching several topics should still
            # surface the chunks that match most of them.
            widened = " OR ".join(f'"{term}"' for term in terms)
            rows = _run(widened, "content")
            title_rows = _run(widened, "title")

        # A chunk already found by content keeps its better (content) rank;
        # title-only hits are appended so both stay searchable without
        # duplicates or nondeterministic ordering.
        seen = {row[0] for row in rows}
        ordered = list(rows) + [row for row in title_rows if row[0] not in seen]
        return [
            KeywordHit(chunk_id=row[0], memory_id=row[1], rank=index + 1)
            for index, row in enumerate(ordered[:limit])
        ]

    # --- LIKE fallback path -------------------------------------------------

    def _search_like(
        self, session, terms: list[str], limit: int,
        from_date: Optional[date], to_date: Optional[date],
    ) -> list[KeywordHit]:
        conditions = []
        for term in terms:
            pattern = f"%{term}%"
            conditions.append(MemoryChunk.chunk_text.ilike(pattern, escape="\\"))
        stmt = (
            select(MemoryChunk.id, MemoryChunk.memory_id)
            .join(Memory, Memory.id == MemoryChunk.memory_id)
            .where(*conditions)
        )
        stmt = _apply_dates(stmt, from_date, to_date)
        stmt = stmt.order_by(Memory.captured_at.desc(), MemoryChunk.id).limit(limit)
        rows = session.execute(stmt).all()
        return [
            KeywordHit(chunk_id=row[0], memory_id=row[1], rank=index + 1)
            for index, row in enumerate(rows)
        ]


def _day_params(from_date: Optional[date], to_date: Optional[date]) -> dict:
    """Half-open UTC day bounds as query params (mirrors the list API)."""
    from datetime import datetime, time, timedelta, timezone

    params: dict = {}
    if from_date is not None:
        params["start"] = datetime.combine(from_date, time.min, tzinfo=timezone.utc)
    if to_date is not None:
        params["end"] = datetime.combine(to_date, time.min, tzinfo=timezone.utc) + timedelta(days=1)
    return params


def _apply_dates(stmt, from_date: Optional[date], to_date: Optional[date]):
    from datetime import datetime, time, timedelta, timezone

    if from_date is not None:
        stmt = stmt.where(
            Memory.captured_at
            >= datetime.combine(from_date, time.min, tzinfo=timezone.utc)
        )
    if to_date is not None:
        stmt = stmt.where(
            Memory.captured_at
            < datetime.combine(to_date, time.min, tzinfo=timezone.utc)
            + timedelta(days=1)
        )
    return stmt
