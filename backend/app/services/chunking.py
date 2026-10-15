"""Deterministic memory chunking for retrieval (Module 6, Task 6.1).

Turns a stored memory's normalized text into ordered, searchable chunks while
preserving offsets into the original text so every chunk can be traced back to
its origin. The original memory record is never mutated.

Strategy: sentence-window v1
-----------------------------
Sentences are the atomic unit. A window packs as many consecutive sentences as
fit into ``chunk_size`` characters; the next window starts one sentence after
the previous window's last full sentence, rewound so roughly ``overlap``
characters of prior context are repeated — without ever starting (or ending) a
chunk mid-sentence. A single sentence longer than ``chunk_size`` (long code
lines, minified text) is hard-split into fixed-size pieces with the same
overlap; that is the only case where a boundary may fall inside a sentence.

Why these defaults (~1200 chars / 150 chars overlap):
  * The local embedding model (nomic-embed-text) accepts up to ~8192 chars, so
    1200 chars (~300 tokens) leaves ample headroom per request.
  * 1200 chars keeps a citation passage small enough to display and to ground
    a single factual claim, while large enough to hold a paragraph of context.
  * 150 chars of overlap (~1-2 sentences) carries context across boundaries at
    a ~12% storage cost.

Determinism: identical (memory_id, text, strategy version, config) inputs
always produce identical chunk ids, texts, and offsets. Chunk ids are
content-derived (``chk_`` + sha256 of memory id, strategy version, index, and
text hash), so an unchanged memory keeps stable ids across reindexing runs,
while a changed memory produces new ids (old rows are replaced
transactionally).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.hashing import content_hash

CHUNK_STRATEGY = "sentence-window"
CHUNK_STRATEGY_VERSION = "v1"

#: Sentence boundaries: terminal punctuation (Latin + CJK) followed by
#: whitespace, or a blank line (paragraph boundary). Lookbehind keeps the
#: punctuation with the preceding sentence.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?。！？])\s+|\n\s*\n")


@dataclass(frozen=True)
class TextChunk:
    """One chunk of a memory's text with stable identity and offsets."""

    chunk_id: str
    chunk_index: int
    start_offset: int
    end_offset: int
    text: str
    content_hash: str
    strategy: str
    strategy_version: str


class ChunkingError(ValueError):
    """Invalid chunking configuration (size/overlap relationship)."""


def chunk_id_for(memory_id: str, index: int, text_hash: str) -> str:
    """Stable, content-derived chunk id.

    Depends on the memory id, strategy version, chunk index, and the chunk
    text's hash — so re-running the chunker over unchanged text reproduces the
    same ids, while different text (or a different strategy version) yields
    different ids and the store replaces rows instead of mixing versions.
    """
    digest = content_hash(
        f"{memory_id}\x00{CHUNK_STRATEGY_VERSION}\x00{index}\x00{text_hash}"
    )
    return f"chk_{digest[:32]}"


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    """Return non-empty (start, end) spans covering ``text`` exactly.

    Splits after sentence-ending punctuation followed by whitespace, or at
    paragraph breaks. Every non-space character belongs to exactly one span,
    which keeps offsets exact and reconstruction lossless.
    """
    spans: list[tuple[int, int]] = []
    start = 0
    for match in _SENTENCE_BOUNDARY.finditer(text):
        end = match.start()
        if end > start:
            spans.append((start, end))
        start = match.end()
    if start < len(text):
        spans.append((start, len(text)))
    return [(s, e) for s, e in spans if text[s:e].strip()]


def _hard_split(text: str, size: int, overlap: int) -> list[tuple[int, int]]:
    """Split a single oversized sentence into (start, end) windows."""
    step = max(size - overlap, 1)
    windows: list[tuple[int, int]] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + size, length)
        windows.append((start, end))
        if end == length:
            break
        start += step
    return windows


def chunk_text(
    text: str,
    memory_id: str,
    chunk_size: int = 1200,
    overlap: int = 150,
) -> list[TextChunk]:
    """Chunk ``text`` deterministically; empty/blank text yields ``[]``.

    Offsets index into ``text`` exactly: ``text[c.start_offset:c.end_offset]
    == c.text``. The original text is not modified.
    """
    if chunk_size < 100:
        raise ChunkingError("chunk_size must be at least 100 characters")
    if overlap < 0 or overlap >= chunk_size:
        raise ChunkingError("overlap must be >= 0 and smaller than chunk_size")
    if not isinstance(text, str) or not text.strip():
        return []

    spans = _sentence_spans(text)
    if not spans:
        return []

    chunks: list[TextChunk] = []
    index = 0

    def emit(start: int, end: int) -> None:
        nonlocal index
        piece = text[start:end]
        if not piece.strip():
            return
        digest = content_hash(piece)
        chunks.append(
            TextChunk(
                chunk_id=chunk_id_for(memory_id, index, digest),
                chunk_index=index,
                start_offset=start,
                end_offset=end,
                text=piece,
                content_hash=digest,
                strategy=CHUNK_STRATEGY,
                strategy_version=CHUNK_STRATEGY_VERSION,
            )
        )
        index += 1

    i = 0
    total = len(spans)
    while i < total:
        start, _ = spans[i]
        end = start
        j = i
        # Pack whole consecutive sentences while they fit the window; the
        # first sentence is always taken (it is then hard-split if oversized).
        while j < total:
            span_end = spans[j][1]
            if j > i and span_end - start > chunk_size:
                break
            end = span_end
            j += 1

        if end - start > chunk_size:
            # A single sentence exceeds the window: hard-split it, with overlap.
            sentence_end = spans[i][1]
            for piece_start, piece_end in _hard_split(
                text[start:sentence_end], chunk_size, overlap
            ):
                emit(start + piece_start, start + piece_end)
            i += 1
            continue

        emit(start, end)

        if j >= total:
            break
        # Next window: first sentence whose start is <= (end - overlap), so the
        # window repeats roughly `overlap` characters of prior context while
        # still starting on a sentence boundary.
        target = end - overlap
        next_i = j
        while next_i > i + 1 and spans[next_i - 1][0] >= target:
            next_i -= 1
        i = next_i if next_i > i else j

    return chunks


def chunk_memory_text(
    text: str,
    memory_id: str,
    chunk_size: int = 1200,
    overlap: int = 150,
) -> list[TextChunk]:
    """Convenience wrapper naming the memory-level use case."""
    return chunk_text(text, memory_id, chunk_size=chunk_size, overlap=overlap)
