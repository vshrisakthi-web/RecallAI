"""SQLAlchemy models for the structured memory database (Module 4)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all database models."""


class Source(Base):
    """An origin shared by one or more saved memories."""

    __tablename__ = "sources"
    __table_args__ = (Index("ix_sources_type_domain", "source_type", "domain"),)

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    identity_key: Mapped[Optional[str]] = mapped_column(
        String(2200), unique=True, nullable=True
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_source_url: Mapped[Optional[str]] = mapped_column(String(2048))
    domain: Mapped[Optional[str]] = mapped_column(String(253), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    memories: Mapped[list["Memory"]] = relationship(back_populates="source")


class Memory(Base):
    """A normalized browser capture, transcript, or manual note."""

    __tablename__ = "memories"
    __table_args__ = (
        Index("ix_memories_captured_at_id", "captured_at", "id"),
        Index("ix_memories_content_hash", "content_hash"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    dedup_key: Mapped[str] = mapped_column(String(2400), nullable=False, unique=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    capture_type: Mapped[Optional[str]] = mapped_column(String(32))
    selected_text: Mapped[Optional[str]] = mapped_column(Text)
    surrounding_context: Mapped[Optional[str]] = mapped_column(Text)
    extraction_status: Mapped[Optional[str]] = mapped_column(String(32))
    note: Mapped[Optional[str]] = mapped_column(Text)
    record_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    source: Mapped[Source] = relationship(back_populates="memories")


class MemoryChunk(Base):
    """A searchable text chunk derived from one memory (Module 6, Task 6.1).

    Chunk rows are derived data: they can always be rebuilt from the memory's
    normalized text. Offsets index into ``Memory.normalized_content``. Source
    metadata (title, URL, type, domain) is joined from ``sources``/``memories``
    at retrieval time instead of being duplicated here. Deleting a memory
    cascades to its chunks; embedding vectors live in ``chunk_embeddings``.
    """

    __tablename__ = "memory_chunks"
    __table_args__ = (
        Index("ix_memory_chunks_memory_id_index", "memory_id", "chunk_index"),
        Index("ix_memory_chunks_source_id", "source_id"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    memory_id: Mapped[str] = mapped_column(
        ForeignKey("memories.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    start_offset: Mapped[int] = mapped_column(nullable=False)
    end_offset: Mapped[int] = mapped_column(nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )


class ChunkEmbedding(Base):
    """A persisted embedding vector for one chunk (Module 6, Task 6.3).

    The vector is a little-endian float32 blob. ``model`` and ``dims`` travel
    with every row so search can exclude vectors from a different model
    generation instead of comparing incompatible spaces.
    """

    __tablename__ = "chunk_embeddings"

    chunk_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("memory_chunks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    memory_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("memories.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    vector: Mapped[bytes] = mapped_column(nullable=False)
    dims: Mapped[int] = mapped_column(nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )


class Conversation(Base):
    """Minimal conversation placeholder for later local-only features."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    title: Mapped[Optional[str]] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )


class Task(Base):
    """Minimal task placeholder; no task queue is created by this module."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="todo")
    input_reference: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )