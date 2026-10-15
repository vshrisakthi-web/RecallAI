"""RecallAI MCP Memory Server.

Read-only Model Context Protocol server over stdio. Reuses the Module 3-6
service layer and the SAME SQLite database as FastAPI (RECALLAI_DB_PATH,
default backend/data/recallai.db). No rewrite, no second database, no
network access. Exposes exactly four tools; no SQL, filesystem, secret, or
shell capabilities.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI
from mcp.server import MCPServer as FastMCP

from app.core.config import settings
from app.database.session import get_session_local
from app.repositories.base import StorageError
from app.repositories.chunk_store import ChunkRepository
from app.repositories.sqlite_store import MemoryRepository
from app.repositories.vector_store import VectorStore
from app.services.embeddings import EmbeddingService
from app.services.evidence import RetrievalInputError, RetrievalUnavailableError
from app.services.hashing import is_safe_id
from app.services.vectors import unpack_vector

logger = logging.getLogger("recallai.mcp.server")

MAX_QUERY_CHARS = 1000
MAX_EXCERPT_CHARS = 600
MAX_LIMIT = 100
MIN_LIMIT = 1


class _MCPInputError(ValueError):
    """Raised for malformed MCP tool arguments (safe to surface)."""


def _positive_int(value: object, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise _MCPInputError(
            f"expected an integer between {minimum} and {maximum}, got {value!r}"
        )
    if value < minimum or value > maximum:
        raise _MCPInputError(
            f"integer must be between {minimum} and {maximum}, got {value}"
        )
    return value


def _bounded_limit(value: object = 20) -> int:
    try:
        return _positive_int(value, MIN_LIMIT, MAX_LIMIT)
    except _MCPInputError as exc:
        raise _MCPInputError(str(exc)) from exc


def _bounded_query(value: object) -> str:
    if not isinstance(value, str):
        raise _MCPInputError("query must be a string.")
    normalized = value.strip()
    if not normalized:
        raise _MCPInputError("query must not be empty.")
    if len(normalized) > MAX_QUERY_CHARS:
        raise _MCPInputError(
            f"query must be <= {MAX_QUERY_CHARS} characters; got {len(normalized)}."
        )
    return normalized


def _safe_memory_id(value: object) -> str:
    if not isinstance(value, str) or not is_safe_id(value):
        raise _MCPInputError(
            "memory_id must be a non-empty string of letters, digits, '.', '_', or '-'."
        )
    return value


def _parse_iso_date(value: Optional[str]) -> Optional[date]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _MCPInputError(f"date must be an ISO date string, got {value!r}")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise _MCPInputError(f"invalid ISO date {value!r}: {exc}") from exc


def _iso(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _truncate(text: Any, bound: int = MAX_EXCERPT_CHARS) -> str:
    s = text if isinstance(text, str) else ("" if text is None else str(text))
    return s if len(s) <= bound else s[:bound] + "…"

PART1_DONE = True


def _serialize_memory(record: Any) -> dict:
    """Expose only safe memory fields. Never content_hash/request_id/paths."""
    return {
        "memory_id": getattr(record, "id", None),
        "title": getattr(record, "title", ""),
        "content": getattr(record, "normalized_text", ""),
        "source_type": getattr(record, "source_type", None),
        "source_id": getattr(record, "source_id", None),
        "source_url": getattr(record, "source_url", None),
        "domain": getattr(record, "domain", None),
        "source_metadata": getattr(record, "source_metadata", {}) or {},
        "captured_at": _iso(getattr(record, "captured_at", None)),
        "ingested_at": _iso(getattr(record, "ingested_at", None)),
    }


def _serialize_evidence(item: Any) -> dict:
    return {
        "memory_id": item.memory_id,
        "chunk_id": item.chunk_id,
        "title": item.source_title,
        "excerpt": _truncate(item.passage),
        "source_id": item.source_id,
        "source_type": item.source_type,
        "source_url": item.source_url,
        "domain": item.domain,
        "captured_at": _iso(item.captured_at),
        "similarity": item.similarity,
        "score": item.score,
        "matched_by": list(item.matched_by),
        "keyword_rank": item.keyword_rank,
    }


class RecallAIMemoryTools:
    """Thin read-only adapter. Delegates everything to existing services."""

    def __init__(
        self,
        sessions: Any = None,
        *,
        memories: Optional[MemoryRepository] = None,
        chunks: Optional[ChunkRepository] = None,
        vectors: Optional[VectorStore] = None,
        embeddings: Optional[EmbeddingService] = None,
        hybrid: Any = None,
    ) -> None:
        from app.services.hybrid import HybridRetrievalService

        factory = sessions or get_session_local()
        self._memories = memories or MemoryRepository(factory)
        self._chunks = chunks or ChunkRepository(factory)
        self._vectors = vectors or VectorStore(factory)
        self._embeddings = embeddings or EmbeddingService()
        self._hybrid = hybrid or HybridRetrievalService(
            self._memories, self._chunks, self._vectors,
            embeddings=self._embeddings, sessions=factory,
        )

    def search_memories(self, query: str, limit: int = 20) -> dict:
        """Ranked hybrid evidence. Mirrors HybridRetrievalService.retrieve()."""
        query_text = _bounded_query(query)
        top_k = _bounded_limit(limit)
        result = self._hybrid.retrieve(question=query_text, top_k=top_k)
        evidence = [_serialize_evidence(e) for e in result.evidence[:top_k]]
        temporal = result.temporal
        return {
            "query": query_text,
            "limit": top_k,
            "evidence": evidence,
            "candidates_considered": result.candidates_considered,
            "temporal": (
                None if temporal is None else {
                    "from_date": _iso(temporal.from_date),
                    "to_date": _iso(temporal.to_date),
                    "expression": temporal.expression,
                }
            ),
            "channels": list(result.channels),
        }

    def get_memory(self, memory_id: str) -> dict:
        """One memory by ID. Safe-ID gate + safe serialization."""
        mid = _safe_memory_id(memory_id)
        record = self._memories.get_by_id(mid)
        if record is None:
            raise LookupError(f"memory {mid!r} was not found.")
        return _serialize_memory(record)
    def search_sources_by_date(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        source_type: Optional[str] = None,
        limit: int = 20,
    ) -> dict:
        """Date-range listing via MemoryRepository.list_memories()."""
        start = _parse_iso_date(start_date)
        end = _parse_iso_date(end_date)
        if start is not None and end is not None and start > end:
            raise _MCPInputError("start_date must not be after end_date.")
        page_size = _bounded_limit(limit)
        if source_type is not None and not isinstance(source_type, str):
            raise _MCPInputError("source_type must be a string.")
        items, total = self._memories.list_memories(
            query=None, from_date=start, to_date=end,
            source_type=source_type, page=1, page_size=page_size,
        )
        return {
            "start_date": start.isoformat() if start else None,
            "end_date": end.isoformat() if end else None,
            "source_type": source_type,
            "limit": page_size,
            "total": total,
            "memories": [_serialize_memory(r) for r in items],
        }

    def get_related_memories(self, memory_id: str, limit: int = 20) -> dict:
        """Related memories from STORED vectors only. No new embeddings."""
        mid = _safe_memory_id(memory_id)
        top_k = _bounded_limit(limit)
        anchor = self._memories.get_by_id(mid)
        if anchor is None:
            raise LookupError(f"memory {mid!r} was not found.")
        chunks = self._chunks.get_chunks(mid)
        if not chunks:
            return {"memory_id": mid, "related_memories": [], "count": 0}
        seen: dict[str, float] = {}
        for chunk in chunks:
            stored = self._vectors.get(chunk.id)
            if stored is None:
                continue
            try:
                vector = unpack_vector(stored.vector, stored.dims)
            except ValueError:
                continue
            try:
                hits = self._vectors.search(
                    vector, stored.model, top_k=top_k + 1, min_similarity=None,
                )
            except StorageError:
                continue
            for hit in hits:
                if hit.memory_id == mid or not is_safe_id(hit.memory_id):
                    continue
                if hit.memory_id not in seen or hit.score > seen[hit.memory_id]:
                    seen[hit.memory_id] = hit.score
        ranked = sorted(seen.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        related = []
        for rel_id, score in ranked:
            record = self._memories.get_by_id(rel_id)
            if record is None:
                continue
            related.append({
                "memory_id": rel_id,
                "title": record.title,
                "score": score,
                "source_type": record.source_type,
                "domain": record.domain,
                "captured_at": _iso(record.captured_at),
            })
        return {"memory_id": mid, "related_memories": related, "count": len(related)}


_TOOLS_SINGLETON: Optional[RecallAIMemoryTools] = None


def get_tools() -> RecallAIMemoryTools:
    """One shared adapter bound to the configured database."""
    global _TOOLS_SINGLETON
    if _TOOLS_SINGLETON is None:
        _TOOLS_SINGLETON = RecallAIMemoryTools()
        logger.info(
            "RecallAI MCP tools bound to DB=%s", settings.database_path
        )
    return _TOOLS_SINGLETON


def _safe_call(label: str, func: Any, *args: Any, **kwargs: Any) -> str:
    try:
        return json.dumps(func(*args, **kwargs), ensure_ascii=False, sort_keys=True)
    except (_MCPInputError, RetrievalInputError, LookupError) as exc:
        logger.info("MCP %s input error: %s", label, exc)
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    except (RetrievalUnavailableError, StorageError) as exc:
        logger.warning("MCP %s unavailable: %r", label, exc)
        return json.dumps(
            {"error": "The memory service is temporarily unavailable."},
            ensure_ascii=False,
        )
    except Exception as exc:  # never leak internals to the client
        logger.exception("MCP %s failed: %r", label, exc)
        return json.dumps(
            {"error": "The memory service encountered an unexpected error."},
            ensure_ascii=False,
        )


def build_mcp() -> FastMCP:
    """Construct the MCP server with exactly four read-only tools."""
    mcp: FastMCP = FastMCP("recallai-mcp")

    @mcp.tool()
    def search_memories(query: str, limit: int = 20) -> str:
        """Search memories (hybrid retrieval). Read-only. JSON string result."""
        return _safe_call(
            "search_memories", get_tools().search_memories, query, limit
        )

    @mcp.tool()
    def get_memory(memory_id: str) -> str:
        """Fetch one memory by ID. Read-only. JSON string result."""
        return _safe_call("get_memory", get_tools().get_memory, memory_id)

    @mcp.tool()
    def search_sources_by_date(
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        source_type: Optional[str] = None,
        limit: int = 20,
    ) -> str:
        """List memories in an ISO date range. Read-only. JSON string result."""
        return _safe_call(
            "search_sources_by_date",
            get_tools().search_sources_by_date,
            start_date, end_date, source_type, limit,
        )

    @mcp.tool()
    def get_related_memories(memory_id: str, limit: int = 20) -> str:
        """Related memories from stored vectors. Read-only. JSON result."""
        return _safe_call(
            "get_related_memories",
            get_tools().get_related_memories, memory_id, limit,
        )

    return mcp


def create_app() -> FastAPI:
    """FastAPI factory for local smoke-testing (uvicorn). Not the MCP path."""
    app = FastAPI(
        title="RecallAI MCP Memory Server",
        description="Read-only MCP server exposing RecallAI memory tools",
        version="0.1.0",
    )

    @app.get("/mcpserver/status", response_model=dict)
    def status() -> dict:
        return {
            "status": "running",
            "service": "MCP Memory Server",
            "version": "0.1.0",
        }

    return app


def main() -> None:
    """Run the MCP server on stdio. Local-only: no port, no CORS, no network."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    logger.info(
        "Starting RecallAI MCP server (stdio). Read-only. DB=%s",
        settings.database_path,
    )
    build_mcp().run()


if __name__ == "__main__":
    main()
