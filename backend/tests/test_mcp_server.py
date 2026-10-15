"""Module 7 — MCP server tests (Tasks 62-68).

Exercises the read-only MCP tool adapter against an isolated migrated
SQLite database. Hybrid retrieval is substituted with a fake so no
embedding model, network, or credentials are ever needed. Covers valid
inputs/outputs, empty/overlong queries, invalid IDs and dates, missing
memories, empty results, invalid limits, missing vectors, service
failures, schema consistency, and read-only/privacy guarantees.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

pytest.importorskip("mcp")  # main .venv (py3.9) has no MCP SDK; skip cleanly

from sqlalchemy.orm import sessionmaker

from app.database.session import create_database_engine
from app.mcp_server.server import (
    MAX_QUERY_CHARS,
    RecallAIMemoryTools,
    _bounded_limit,
    _bounded_query,
    _MCPInputError,
    _parse_iso_date,
    _safe_call,
    _safe_memory_id,
    _serialize_memory,
    build_mcp,
    create_app,
)
from app.repositories.chunk_store import ChunkRepository
from app.repositories.sqlite_store import MemoryRepository
from app.repositories.vector_store import VectorStore
from app.services.embeddings import EmbeddingService
from app.services.evidence import (
    Evidence,
    RetrievalInputError,
    RetrievalResult,
    RetrievalUnavailableError,
)
from app.services.temporal import NormalizedQuery
from app.services.vectors import pack_vector
from tests._factories import make_record

MODEL = "unit-test-model"


class _FakeHybrid:
    """Offline stand-in for HybridRetrievalService.retrieve()."""

    def __init__(self, result=None, error=None):
        self.calls: list = []
        self._result = result
        self._error = error

    def retrieve(self, question, top_k=None, from_date=None, to_date=None):
        self.calls.append((question, top_k, from_date, to_date))
        if self._error is not None:
            raise self._error
        return self._result


def _result(evidence=(), temporal=None, channels=("keyword",)):
    query = NormalizedQuery(original="q", text="q", temporal=temporal)
    return RetrievalResult(
        query=query,
        evidence=list(evidence),
        candidates_considered=len(evidence),
        temporal=temporal,
        channels=tuple(channels),
    )


def _evidence(memory_id="mem_a", **overrides):
    base = {
        "chunk_id": f"chk_{memory_id}",
        "memory_id": memory_id,
        "passage": "stored passage text",
        "source_id": "src_1",
        "source_type": "note",
        "source_title": "Title",
        "source_url": None,
        "domain": None,
        "captured_at": datetime(2024, 5, 1, tzinfo=timezone.utc),
        "similarity": 0.9,
        "keyword_rank": 1,
        "score": 0.05,
        "matched_by": ("keyword",),
    }
    base.update(overrides)
    return Evidence(**base)


@pytest.fixture()
def database_engine(tmp_path):
    from alembic import command
    from alembic.config import Config

    engine = create_database_engine(str(tmp_path / "mcp.db"))
    config = Config("alembic.ini")
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    yield engine
    engine.dispose()


@pytest.fixture()
def tools(database_engine):
    sessions = sessionmaker(bind=database_engine, expire_on_commit=False)
    memories = MemoryRepository(sessions)
    chunks = ChunkRepository(sessions)
    vectors = VectorStore(sessions)
    hybrid = _FakeHybrid(_result())
    return RecallAIMemoryTools(
        sessions,
        memories=memories, chunks=chunks, vectors=vectors, hybrid=hybrid,
    )


def test_mcp_server_imports_and_registers_four_tools():
    mcp = build_mcp()
    assert sorted(mcp._tool_manager._tools.keys()) == [
        "get_memory",
        "get_related_memories",
        "search_memories",
        "search_sources_by_date",
    ]
    assert create_app().title == "RecallAI MCP Memory Server"


def test_validation_helpers_reject_bad_inputs():
    for bad in ["", "   ", 123, None, "x" * (MAX_QUERY_CHARS + 1)]:
        with pytest.raises(_MCPInputError):
            _bounded_query(bad)
    assert _bounded_query("  ok  ") == "ok"
    for bad in [0, -1, 101, 1.5, True, "5", None]:
        with pytest.raises(_MCPInputError):
            _bounded_limit(bad)
    assert _bounded_limit(5) == 5
    for bad in ["nope", "2024-13-01", "01/05/2024", 123]:
        with pytest.raises(_MCPInputError):
            _parse_iso_date(bad)
    assert _parse_iso_date("2024-05-01") == date(2024, 5, 1)
    assert _parse_iso_date(None) is None
    for bad in ["", "../x", "a/b", "x" * 65, None, 123]:
        with pytest.raises(_MCPInputError):
            _safe_memory_id(bad)
    assert _safe_memory_id("mem_abc-123.X") == "mem_abc-123.X"


def test_search_memories_returns_serialized_evidence(tools):
    tools._hybrid._result = _result([_evidence("mem_a"), _evidence("mem_b")])
    out = tools.search_memories("vector search", 2)
    assert out["query"] == "vector search"
    assert out["limit"] == 2
    assert [e["memory_id"] for e in out["evidence"]] == ["mem_a", "mem_b"]
    first = out["evidence"][0]
    assert first["title"] == "Title"
    assert first["excerpt"] == "stored passage text"
    assert first["captured_at"] == "2024-05-01T00:00:00+00:00"
    assert first["matched_by"] == ["keyword"]
    assert out["channels"] == ["keyword"]
    assert tools._hybrid.calls[0][0] == "vector search"
    assert tools._hybrid.calls[0][1] == 2
    json.dumps(out)  # must be JSON-serializable


def _seed(memories, **overrides):
    record, _ = memories.save_or_get(make_record(**overrides))
    return record


def test_search_memories_empty_and_trims_to_limit(tools):
    tools._hybrid._result = _result([])
    out = tools.search_memories("nothing matches")
    assert out["evidence"] == []
    assert out["candidates_considered"] == 0
    tools._hybrid._result = _result([_evidence(f"mem_{i}") for i in range(5)])
    out = tools.search_memories("q", 3)
    assert len(out["evidence"]) == 3


def test_search_memories_input_errors_propagate(tools):
    with pytest.raises(_MCPInputError):
        tools.search_memories("")
    with pytest.raises(_MCPInputError):
        tools.search_memories("x" * (MAX_QUERY_CHARS + 1))
    with pytest.raises(_MCPInputError):
        tools.search_memories("ok", 0)
    tools._hybrid._error = RetrievalInputError("bad question")
    with pytest.raises(RetrievalInputError):
        tools.search_memories("ok")
    tools._hybrid._error = RetrievalUnavailableError("model down")
    with pytest.raises(RetrievalUnavailableError):
        tools.search_memories("ok")


def test_get_memory_round_trip_and_safe_shape(tools):
    record = _seed(tools._memories, id="mem_mcp1", title="MCP One")
    out = tools.get_memory("mem_mcp1")
    assert out["memory_id"] == "mem_mcp1"
    assert out["title"] == "MCP One"
    assert out["content"] == record.normalized_text
    assert out["captured_at"] is not None
    assert "content_hash" not in out
    assert "request_id" not in out
    json.dumps(out)


def test_get_memory_rejects_bad_and_missing_ids(tools):
    for bad in ["", "../escape", "a/b", "x" * 65, None, 123]:
        with pytest.raises(_MCPInputError):
            tools.get_memory(bad)
    with pytest.raises(LookupError):
        tools.get_memory("mem_nope_missing")


def test_search_sources_by_date_filters_and_validates(tools):
    # distinct _text => distinct content_hash; otherwise save_or_get dedupes
    # both records into one row (dedup key includes content_hash).
    _seed(tools._memories, id="mem_may", title="May note",
          _text="body of the may note",
          captured_at=datetime(2024, 5, 10, tzinfo=timezone.utc))
    _seed(tools._memories, id="mem_jun", title="June note",
          _text="body of the june note",
          captured_at=datetime(2024, 6, 10, tzinfo=timezone.utc))
    out = tools.search_sources_by_date("2024-05-01", "2024-05-31")
    assert out["total"] == 1
    assert out["memories"][0]["memory_id"] == "mem_may"
    assert out["start_date"] == "2024-05-01"
    out_all = tools.search_sources_by_date()
    assert out_all["total"] == 2
    assert out_all["start_date"] is None
    with pytest.raises(_MCPInputError):
        tools.search_sources_by_date("2024-06-01", "2024-05-01")
    with pytest.raises(_MCPInputError):
        tools.search_sources_by_date("not-a-date", None)
    with pytest.raises(_MCPInputError):
        tools.search_sources_by_date(limit=0)
    json.dumps(out_all)


def test_get_related_memories_empty_without_chunks(tools):
    _seed(tools._memories, id="mem_lone", title="Lone")
    out = tools.get_related_memories("mem_lone")
    assert out == {"memory_id": "mem_lone", "related_memories": [], "count": 0}
    with pytest.raises(_MCPInputError):
        tools.get_related_memories("bad/id")
    with pytest.raises(LookupError):
        tools.get_related_memories("mem_missing_xyz")


def test_get_related_memories_uses_stored_vectors(tools):
    from app.services.chunking import chunk_text

    anchor = _seed(tools._memories, id="mem_anchor", title="Anchor",
                   _text="anchor text about databases and indexes")
    rel = _seed(tools._memories, id="mem_rel", title="Related",
                _text="related text about databases and query planning")
    tools._chunks.replace_memory_chunks(
        anchor.id, chunk_text(anchor.normalized_text, anchor.id))
    tools._chunks.replace_memory_chunks(
        rel.id, chunk_text(rel.normalized_text, rel.id))
    vec_a = [1.0, 0.0, 0.0]
    vec_r = [0.9, 0.1, 0.0]
    for chunk in tools._chunks.get_chunks(anchor.id):
        tools._vectors.upsert(chunk.id, anchor.id, vec_a, MODEL)
    for chunk in tools._chunks.get_chunks(rel.id):
        tools._vectors.upsert(chunk.id, rel.id, vec_r, MODEL)
    out = tools.get_related_memories(anchor.id)
    ids = [r["memory_id"] for r in out["related_memories"]]
    assert rel.id in ids
    assert anchor.id not in ids
    assert out["count"] == len(out["related_memories"])
    json.dumps(out)


def test_get_related_memories_skips_missing_and_deleted(tools):
    from app.services.chunking import chunk_text

    anchor = _seed(tools._memories, id="mem_a2", title="A2",
                   _text="anchor sentence one. anchor sentence two.")
    ghost = _seed(tools._memories, id="mem_ghost", title="Ghost",
                  _text="ghost sentence one. ghost sentence two.")
    tools._chunks.replace_memory_chunks(
        anchor.id, chunk_text(anchor.normalized_text, anchor.id))
    tools._chunks.replace_memory_chunks(
        ghost.id, chunk_text(ghost.normalized_text, ghost.id))
    vec = [1.0, 0.0]
    anchor_chunk_ids = [c.id for c in tools._chunks.get_chunks(anchor.id)]
    ghost_chunk_ids = [c.id for c in tools._chunks.get_chunks(ghost.id)]
    tools._vectors.upsert(anchor_chunk_ids[0], anchor.id, vec, MODEL)
    tools._vectors.upsert(ghost_chunk_ids[0], ghost.id, vec, MODEL)
    assert tools._memories.delete_by_id(ghost.id) is True
    out = tools.get_related_memories(anchor.id)
    assert all(r["memory_id"] != anchor.id for r in out["related_memories"])
    assert all(r["memory_id"] != ghost.id for r in out["related_memories"])


def test_database_failures_surface_safely(tools):
    from app.repositories.base import StorageError

    class _Broken:
        def get_by_id(self, _rid):
            raise StorageError("disk gone")

        def list_memories(self, **_kw):
            raise StorageError("disk gone")

    broken = RecallAIMemoryTools(
        memories=_Broken(), chunks=tools._chunks, vectors=tools._vectors,
        hybrid=tools._hybrid,
    )
    with pytest.raises(StorageError):
        broken.get_memory("mem_okfine")
    with pytest.raises(StorageError):
        broken.search_sources_by_date()


def test_serialize_memory_never_exposes_secrets(tools):
    record = _seed(tools._memories, id="mem_priv", title="Priv")
    out = _serialize_memory(record)
    blob = json.dumps(out)
    assert record.content_hash not in blob
    assert record.request_id not in blob
    assert set(out) == {
        "memory_id", "title", "content", "source_type", "source_id",
        "source_url", "domain", "source_metadata", "captured_at", "ingested_at",
    }


def test_read_only_no_write_tools_registered():
    import app.mcp_server.server as srv

    mcp = build_mcp()
    names = sorted(mcp._tool_manager._tools.keys())
    assert names == [
        "get_memory", "get_related_memories",
        "search_memories", "search_sources_by_date",
    ]
    source = open(srv.__file__).read()
    for forbidden in ["delete_by_id", "save_or_get", "replace_memory_chunks",
                      "upsert(", "subprocess", "os.system"]:
        assert forbidden not in source


def test_safe_call_envelopes_never_leak_internals():
    from app.repositories.base import StorageError

    # safe input error -> safe message, no traceback
    out = json.loads(_safe_call("t", _bounded_query, ""))
    assert "error" in out and "empty" in out["error"]
    # unsafe id -> safe message
    out = json.loads(_safe_call("t", _safe_memory_id, "bad/id"))
    assert "memory_id" in out["error"]
    # retrieval/storage unavailable -> canned message, internals stay in logs
    def _down():
        raise StorageError("disk gone at /var/db/secret.db")

    def _unavail():
        raise RetrievalUnavailableError("model offline at /models/x")

    for boom in (_down, _unavail):
        out = json.loads(_safe_call("t", boom))
        assert out == {"error": "The memory service is temporarily unavailable."}
    # anything else -> canned message with no traceback, path, or cause text
    def _boom():
        raise RuntimeError("secret /Users/shrisakthi/projects/RecallAI/backend/app/x.py")

    out = json.loads(_safe_call("t", _boom))
    assert out == {"error": "The memory service encountered an unexpected error."}
    blob = json.dumps(out)
    for leak in ("Traceback", "secret", "backend", "/Users/", "RuntimeError"):
        assert leak not in blob

