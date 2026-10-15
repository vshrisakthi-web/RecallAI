"""Task 6.4 — temporal parsing tests.

Pure unit tests (no database, no network): yesterday/last-week/month
windows, year and month boundaries, specificity precedence, case handling,
ambiguous expressions returning no filter, and query validation.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.services.temporal import (
    QueryInputError,
    normalize_and_parse,
    normalize_query,
    parse_temporal,
)

# Monday 2026-10-12, 12:00 UTC — a fixed "now" for deterministic tests.
NOW = datetime(2026, 10, 12, 12, 0, 0, tzinfo=timezone.utc)


def test_normalize_trims_and_preserves_original():
    result = normalize_query("  What did I learn?  ")
    assert result.text == "What did I learn?"
    assert result.original == "  What did I learn?  "
    assert result.temporal is None


@pytest.mark.parametrize("bad", ["", "   ", None, 42, "\n\t "])
def test_empty_and_non_string_queries_rejected(bad):
    with pytest.raises(QueryInputError):
        normalize_query(bad)  # type: ignore[arg-type]


def test_oversized_query_rejected():
    with pytest.raises(QueryInputError):
        normalize_query("x" * 50, max_chars=10)


def test_yesterday_is_single_prior_day():
    window = parse_temporal("What did I write yesterday?", NOW)
    assert window is not None
    assert (window.from_date, window.to_date) == (date(2026, 10, 11),) * 2
    assert window.expression == "yesterday"


def test_last_week_is_prior_monday_to_sunday():
    window = parse_temporal("What did I learn about RAG last week?", NOW)
    assert window is not None
    assert window.from_date == date(2026, 10, 5)  # Monday
    assert window.to_date == date(2026, 10, 11)  # Sunday
    assert window.expression == "last week"
    assert (window.to_date - window.from_date).days == 6


def test_last_week_across_month_boundary():
    # Thursday 2026-10-01: prior week spans September into October.
    thursday = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    window = parse_temporal("last week notes", thursday)
    assert window is not None
    assert (window.from_date, window.to_date) == (
        date(2026, 9, 21),
        date(2026, 9, 27),
    )


def test_last_week_across_year_boundary():
    # Friday 2027-01-01: prior week spans December 2026 into January 2027.
    new_year = datetime(2027, 1, 1, 12, tzinfo=timezone.utc)
    window = parse_temporal("last week notes", new_year)
    assert window is not None
    assert (window.from_date, window.to_date) == (
        date(2026, 12, 21),
        date(2026, 12, 27),
    )


def test_in_month_current_year():
    window = parse_temporal("What did I save in September?", NOW)
    assert window is not None
    assert (window.from_date, window.to_date) == (
        date(2026, 9, 1),
        date(2026, 9, 30),
    )


def test_in_month_ahead_means_last_year():
    # "in December" asked in October cannot mean the future.
    window = parse_temporal("What did I save in December?", NOW)
    assert window is not None
    assert (window.from_date, window.to_date) == (
        date(2025, 12, 1),
        date(2025, 12, 31),
    )


def test_in_month_supports_abbreviations_and_leap_february():
    window = parse_temporal("notes from feb", datetime(2024, 6, 15, tzinfo=timezone.utc))
    assert window is not None
    assert (window.from_date, window.to_date) == (
        date(2024, 2, 1),
        date(2024, 2, 29),  # 2024 is a leap year
    )
    assert parse_temporal("notes from sept", NOW) is not None


def test_expressions_are_case_insensitive_whole_words():
    assert parse_temporal("YESTERDAY notes", NOW) is not None
    assert parse_temporal("LAST  WEEK notes", NOW) is not None
    assert parse_temporal("IN SEPTEMBER notes", NOW) is not None
    # "yesterdays" and "weekly" are not temporal expressions.
    assert parse_temporal("yesterdays news", NOW) is None
    assert parse_temporal("weekly review notes", NOW) is None


def test_most_specific_expression_wins():
    window = parse_temporal("What did I learn yesterday and last week?", NOW)
    assert window is not None
    assert window.expression == "yesterday"
    assert (window.from_date, window.to_date) == (date(2026, 10, 11),) * 2


def test_ambiguous_expressions_return_no_filter():
    for vague in [
        "What did I learn recently?",
        "Notes from a while ago",
        "What did I do last summer?",
        "What did I learn about RAG?",
        "Show me everything",
    ]:
        assert parse_temporal(vague, NOW) is None


def test_naive_now_is_interpreted_as_utc():
    naive = datetime(2026, 10, 12, 12, 0, 0)  # no tzinfo
    window = parse_temporal("notes from yesterday", naive)
    assert window is not None
    assert (window.from_date, window.to_date) == (date(2026, 10, 11),) * 2


def test_normalize_and_parse_attaches_temporal():
    result = normalize_and_parse("  What did I learn last week? ", NOW)
    assert result.text == "What did I learn last week?"
    assert result.temporal is not None
    assert result.temporal.from_date == date(2026, 10, 5)
    assert result.temporal.to_date == date(2026, 10, 11)
