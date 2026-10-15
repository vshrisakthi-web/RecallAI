"""Query normalization and temporal-expression parsing (Module 6, Task 6.4).

Plain English: a question like "What did I learn about RAG last week?"
contains two things — the *topic* ("RAG") and a *time window* ("last week").
This module splits those apart: the topic goes to the embedding model
unchanged, and the time window becomes explicit ``from_date``/``to_date``
filters using the same day-granular conventions as the memories list API
(``[from_date, to_date]`` inclusive on both ends, compared against the
memory's ``captured_at`` event time in UTC).

Supported expressions (case-insensitive, matched as whole words):
  * "yesterday"   -> the single calendar day before today.
  * "last week"   -> the previous Monday-to-Sunday week (ISO week).
  * "<prep> <Month>" with prep in {in, from, during, for} -> that month.
    If the month is still ahead of us this year (e.g. "in December" asked
    means this year. No day is ever guessed.

Boundary rule, documented once here: "last week" asked on Monday 2026-10-12
means Mon 2026-10-05 through Sun 2026-10-11. "Yesterday" means the whole
calendar day, 00:00 to 24:00 UTC. Month filters cover the whole calendar
month. All intervals are inclusive on both ends.

Ambiguity policy: only the three patterns above are recognized. Anything
else ("recently", "a while ago", "last summer") returns no filter rather
than a guess — the caller retrieves unfiltered instead of pretending it
understood a date. When several expressions appear, "yesterday" wins over
"last week" wins over "in <Month>" (most specific first), and the match is
reported so callers can show the user what was assumed.

"Now" is an explicit parameter (never read from the clock inside) so tests
are deterministic.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from app.core.config import settings


class QueryInputError(ValueError):
    """Raised when a question is empty or exceeds the configured limit."""


@dataclass(frozen=True)
class TemporalFilter:
    """An explicit calendar window parsed from the question text."""

    from_date: date
    to_date: date
    expression: str  # the matched phrase, e.g. "last week"


@dataclass(frozen=True)
class NormalizedQuery:
    """A validated question plus its optional temporal filter."""

    original: str  # untouched, for display/audit
    text: str  # stripped query; meaning is never rewritten
    temporal: Optional[TemporalFilter]


_MONTHS = {name.lower(): number for number, name in enumerate(calendar.month_name) if name}
_MONTHS.update({name.lower(): number for number, name in enumerate(calendar.month_abbr) if name})
_MONTHS["sept"] = 9  # common abbreviation missing from calendar.month_abbr

_YESTERDAY = re.compile(r"\byesterday\b", re.IGNORECASE)
_LAST_WEEK = re.compile(r"\blast\s+week\b", re.IGNORECASE)
_IN_MONTH = re.compile(
    r"\b(?:in|from|during|for)\s+(january|february|march|april|may|june|"
    r"july|august|september|october|november|december|jan|feb|mar|apr|"
    r"jun|jul|aug|sept|sep|oct|nov|dec)\b",
    re.IGNORECASE,
)


def normalize_query(question: object, max_chars: Optional[int] = None) -> NormalizedQuery:
    """Validate a question and split off any temporal filter.

    ``now`` is intentionally not read here — pass it explicitly via
    ``parse_temporal`` when the caller needs time-relative filters. This
    function only validates; the temporal pass is separate so retrieval can
    reuse one ``now`` for the whole request.
    """
    if not isinstance(question, str) or not question.strip():
        raise QueryInputError("The question must not be empty.")
    limit = settings.rag_max_question_chars if max_chars is None else max_chars
    text = question.strip()
    if len(text) > limit:
        raise QueryInputError(
            f"The question exceeds the {limit}-character limit."
        )
    return NormalizedQuery(original=question, text=text, temporal=None)


def parse_temporal(question: str, now: datetime) -> Optional[TemporalFilter]:
    """Extract a calendar window from the question, or None if unrecognized."""
    today = now.astimezone(timezone.utc).date()
    yesterday_match = _YESTERDAY.search(question)
    if yesterday_match:
        day = today - timedelta(days=1)
        return TemporalFilter(from_date=day, to_date=day, expression="yesterday")
    last_week_match = _LAST_WEEK.search(question)
    if last_week_match:
        this_monday = today - timedelta(days=today.weekday())
        start = this_monday - timedelta(days=7)
        end = this_monday - timedelta(days=1)
        return TemporalFilter(from_date=start, to_date=end, expression="last week")
    month_match = _IN_MONTH.search(question)
    if month_match:
        month = _MONTHS[month_match.group(1).lower()]
        year = today.year
        if month > today.month:
            # A month still ahead of us this year must mean last year —
            # "in December" asked in October cannot mean the future.
            year -= 1
        _, last_day = calendar.monthrange(year, month)
        return TemporalFilter(
            from_date=date(year, month, 1),
            to_date=date(year, month, last_day),
            expression=month_match.group(0).lower(),
        )
    return None


def normalize_and_parse(question: object, now: datetime) -> NormalizedQuery:
    """Validate the question and attach its temporal filter (if any)."""
    normalized = normalize_query(question)
    return NormalizedQuery(
        original=normalized.original,
        text=normalized.text,
        temporal=parse_temporal(normalized.text, now),
    )
