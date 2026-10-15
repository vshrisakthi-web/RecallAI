"""Vector math for local retrieval (Module 6, Task 6.3).

Embeddings are stored as little-endian float32 blobs and compared with
cosine similarity in pure Python. NumPy is deliberately *not* a dependency:
personal-memory scale (hundreds to low thousands of chunks) keeps brute-force
scan latency in the low milliseconds, and zero new dependencies keeps install
and audit surface minimal.

MVP limitation, stated honestly: similarity search is O(n·d) over the stored
vectors for the active model generation. The ``VectorStore`` interface is
replaceable — when collections grow past ~10k chunks, swap the scan for an
ANN index (sqlite-vec, HNSW) without touching callers. Vectors are loaded
once per search, never cached across writes (no stale-read risk), and the
public API never returns raw vectors.
"""

from __future__ import annotations

import math
import struct


def pack_vector(values: list[float]) -> bytes:
    """Encode a validated embedding as a little-endian float32 blob."""
    return struct.pack(f"<{len(values)}f", *values)


def unpack_vector(blob: bytes, dims: int) -> list[float]:
    """Decode a stored blob; raises on truncation or dimension mismatch."""
    expected = dims * 4
    if len(blob) != expected:
        raise ValueError(
            f"stored vector has {len(blob)} bytes, expected {expected} "
            f"for {dims} dimensions"
        )
    return list(struct.unpack(f"<{dims}f", blob))


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Cosine similarity in [-1, 1]; zero-norm vectors score 0.0, never NaN."""
    if len(left) != len(right):
        raise ValueError("cannot compare vectors of different dimensions")
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    score = dot / (left_norm * right_norm)
    # Clamp float rounding so scores stay inside [-1, 1].
    return max(-1.0, min(1.0, score))
