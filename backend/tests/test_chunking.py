"""Task 6.1 — chunking strategy tests.

Pure unit tests (no database, no network): short notes, long text, sentence
boundaries, overlap, empty/blank input, unicode content, deterministic
identity, and config validation.
"""

from __future__ import annotations

from app.services.chunking import (
    CHUNK_STRATEGY,
    CHUNK_STRATEGY_VERSION,
    ChunkingError,
    chunk_id_for,
    chunk_text,
)
from app.services.hashing import content_hash

import pytest


def test_short_note_is_single_chunk():
    chunks = chunk_text("Buy milk tomorrow morning.", "mem_1")
    assert len(chunks) == 1
    (chunk,) = chunks
    assert chunk.chunk_index == 0
    assert chunk.start_offset == 0
    assert chunk.end_offset == len("Buy milk tomorrow morning.")
    assert chunk.text == "Buy milk tomorrow morning."
    assert chunk.strategy == CHUNK_STRATEGY
    assert chunk.strategy_version == CHUNK_STRATEGY_VERSION
    assert chunk.chunk_id.startswith("chk_")


def test_empty_and_blank_text_yield_no_chunks():
    assert chunk_text("", "mem_1") == []
    assert chunk_text("   \n\t  ", "mem_1") == []
    assert chunk_text(None, "mem_1") == []


def test_deterministic_chunking_for_identical_input():
    text = (
        "Retrieval-augmented generation grounds answers in evidence. "
        "The retriever fetches passages. The generator writes the answer."
    )
    first = chunk_text(text, "mem_1")
    second = chunk_text(text, "mem_1")
    assert [(c.chunk_id, c.text) for c in first] == [
        (c.chunk_id, c.text) for c in second
    ]


def test_different_memory_ids_give_different_chunk_ids():
    text = "Deterministic identity matters for reindexing."
    left = chunk_text(text, "mem_a")
    right = chunk_text(text, "mem_b")
    assert left[0].chunk_id != right[0].chunk_id
    assert left[0].text == right[0].text


def test_sentence_boundaries_are_respected():
    text = "First sentence ends here. Second sentence begins. Third follows."
    chunks = chunk_text(text, "mem_1", chunk_size=100, overlap=10)
    assert chunks
    for chunk in chunks:
        assert chunk.text.strip()
        # No chunk starts or ends in the middle of the second sentence.
        assert not chunk.text.startswith("sentence")
        assert not chunk.text.endswith("Second")


def test_overlap_repeats_context():
    sentences = [f"Sentence number {n} carries context forward." for n in range(40)]
    text = " ".join(sentences)
    chunks = chunk_text(text, "mem_1", chunk_size=200, overlap=60)
    assert len(chunks) >= 3
    for earlier, later in zip(chunks, chunks[1:]):
        # Later chunk starts before the earlier chunk ends (context repeats)...
        assert later.start_offset < earlier.end_offset
        assert later.start_offset >= earlier.end_offset - 60 - 50
        # ...but still on a sentence boundary (preceded by whitespace).
        assert text[later.start_offset - 1].isspace()


def test_unicode_content_is_supported():
    text = "日本語のテスト。RAG は検索拡張生成です。絵文字も大丈夫 😊。 café naïve — über."
    chunks = chunk_text(text, "mem_1")
    assert chunks
    for chunk in chunks:
        assert text[chunk.start_offset:chunk.end_offset] == chunk.text
        chunk.text.encode("utf-8")


def test_long_text_packing_and_ordering():
    sentences = [f"Fact {n}: the bridge spans the river quietly." for n in range(60)]
    text = " ".join(sentences)
    chunks = chunk_text(text, "mem_1", chunk_size=300, overlap=50)
    assert len(chunks) >= 5
    indices = [c.chunk_index for c in chunks]
    assert indices == sorted(indices) == list(range(len(chunks)))
    # Ordered, non-decreasing offsets; windows bounded by size.
    prev_end = 0
    for chunk in chunks:
        assert chunk.start_offset >= prev_end - 100
        assert chunk.end_offset - chunk.start_offset <= 300 + 1
        prev_end = chunk.end_offset
    # The full sentence sequence survives across chunks (no dropped sentences).
    joined = " ".join(c.text for c in chunks)
    assert "Fact 0" in joined and "Fact 59" in joined


def test_oversized_sentence_is_hard_split_with_overlap():
    sentence = "x" * 500  # no sentence boundary; exceeds the window
    chunks = chunk_text(sentence, "mem_1", chunk_size=200, overlap=50)
    assert len(chunks) >= 3
    assert chunks[-1].end_offset == len(sentence)
    for chunk in chunks:
        assert chunk.end_offset - chunk.start_offset <= 200
    assert chunks[1].start_offset < chunks[0].end_offset  # overlap repeats


def test_content_hash_and_offsets_round_trip():
    text = "Alpha. Beta gamma. Delta epsilon zeta eta theta."
    (chunk,) = chunk_text(text, "mem_1")
    assert chunk.content_hash == content_hash(chunk.text)
    assert text[chunk.start_offset:chunk.end_offset] == chunk.text


def test_chunk_id_is_stable_but_text_sensitive():
    text = "Stable ids make reindexing safe."
    digest = content_hash(text)
    first = chunk_id_for("mem_1", 0, digest)
    assert first == chunk_id_for("mem_1", 0, digest)
    assert first != chunk_id_for("mem_1", 1, digest)
    assert first != chunk_id_for("mem_1", 0, content_hash(text + " changed"))


def test_invalid_configuration_is_rejected():
    with pytest.raises(ChunkingError):
        chunk_text("Some text.", "mem_1", chunk_size=50)
    with pytest.raises(ChunkingError):
        chunk_text("Some text.", "mem_1", chunk_size=200, overlap=200)
    with pytest.raises(ChunkingError):
        chunk_text("Some text.", "mem_1", chunk_size=200, overlap=-1)
