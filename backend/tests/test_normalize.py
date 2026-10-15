"""Unit tests for normalization and hashing (Module 3, Task 3.5)."""

from app.services.hashing import content_hash, is_safe_id
from app.services.normalize import is_blank, normalize_text


def test_normalizes_line_endings():
    assert normalize_text("a\r\nb\rc") == "a\nb\nc"


def test_collapses_internal_whitespace():
    assert normalize_text("hello    \t world") == "hello world"


def test_strips_trailing_spaces_per_line():
    assert normalize_text("line one   \nline two\t") == "line one\nline two"


def test_collapses_repeated_blank_lines_to_one():
    assert normalize_text("para one\n\n\n\npara two") == "para one\n\npara two"


def test_preserves_paragraph_boundary():
    assert normalize_text("para one\n\npara two") == "para one\n\npara two"


def test_strips_leading_and_trailing_whitespace():
    assert normalize_text("\n\n   hello   \n\n") == "hello"


def test_preserves_meaningful_punctuation_and_code():
    text = "Run `pip install -r requirements.txt`; note the 50% threshold & <T> generics."
    assert normalize_text(text) == text


def test_empty_and_whitespace_only():
    assert normalize_text("") == ""
    assert normalize_text("   \n\t  ") == ""
    assert is_blank("   \n ") is True
    assert is_blank("x") is False


def test_deterministic():
    # The core guarantee: identical input always yields identical output.
    messy = "Hello   \n\n\n\n   world  "
    assert normalize_text(messy) == normalize_text(messy)


def test_redundant_whitespace_normalizes_to_same_compact_form():
    # Inputs differing only by redundant whitespace normalize identically.
    assert normalize_text("Hello   world") == normalize_text("Hello world")
    assert normalize_text("a\n\n\n\nb") == normalize_text("a\n\nb")


def test_preserves_leading_indentation():
    # We deliberately do not lstrip lines, so code indentation survives.
    assert normalize_text("def f():\n    return 1") == "def f():\n    return 1"


def test_content_hash_stable_and_distinct():
    assert content_hash("hello") == content_hash("hello")
    assert content_hash("hello") != content_hash("hello ")


def test_safe_id_rules():
    assert is_safe_id("mem_abc-123.def")
    assert not is_safe_id("bad id!")
    assert not is_safe_id("a" * 65)
    assert not is_safe_id("")
