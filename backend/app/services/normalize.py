"""Deterministic text normalization (Module 3, Task 3.5).

The backend performs *deterministic cleanup* on text it receives. It does not
attempt to strip webpage navigation from already-extracted text — that is the
extension's job (Module 2). We only normalize whitespace/line-endings while
preserving paragraph boundaries and headings, and never remove meaningful
punctuation, code, or transcript content.

Because the rules are purely mechanical, identical input always produces
identical output — which is what makes the content hash stable for deduplication.
"""

from __future__ import annotations

import re

# 3+ consecutive newlines (with optional surrounding spaces/tabs) -> 2 newlines
# (i.e. at most one blank line between paragraphs).
_BLANK_RUNS = re.compile(r"[ \t]*\n(?:[ \t]*\n)+")
# Runs of spaces/tabs within a line -> a single space.
_SPACE_RUNS = re.compile(r"[ \t]+")
# Leading spaces/tabs at the start of a line (preserved as indentation).
_LEADING_WS = re.compile(r"[ \t]*")


def normalize_text(text: str) -> str:
    """Return the normalized form of ``text``.

    Steps (in order):
    1. Normalize line endings (CRLF / CR -> LF).
    2. Preserve leading indentation (so code blocks survive).
    3. Collapse internal runs of spaces/tabs to one space; strip trailing ws.
    4. Collapse 2+ blank lines into a single blank line (paragraph boundary).
    5. Strip leading/trailing whitespace of the whole text.
    """
    if text is None:
        return ""

    # 1. Normalize line endings.
    s = text.replace("\r\n", "\n").replace("\r", "\n")

    # 2 & 3. Per-line: preserve leading indentation (code blocks), collapse
    # internal runs of spaces/tabs to one space, strip trailing whitespace.
    lines = []
    for line in s.split("\n"):
        indent = _LEADING_WS.match(line).group(0)
        body = line[len(indent):]
        body = _SPACE_RUNS.sub(" ", body).rstrip()
        lines.append(indent + body)

    s = "\n".join(lines)

    # 4. Collapse repeated blank lines to a single blank line.
    s = _BLANK_RUNS.sub("\n\n", s)

    # 5. Trim the whole string.
    return s.strip()


def is_blank(text: str) -> bool:
    """True when the text is empty or contains only whitespace."""
    return text is None or text.strip() == ""
