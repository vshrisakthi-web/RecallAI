"""Create the Module 6 chunk index tables and optional FTS5 index.

Additive only: existing sources/memories tables are untouched, and the
migration is re-runnable over a populated database. ``memory_chunks`` holds
derived data that can always be rebuilt from ``memories.normalized_content``;
``chunk_fts`` mirrors the chunk text for keyword retrieval with triggers on
insert/update/delete (keyword hybrid search, Task 6.5). Embedding vectors live
in ``chunk_embeddings`` (Task 6.3 migration).
"""

from __future__ import annotations

from logging import getLogger
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.exc import OperationalError

revision: str = "20261011_0002"
down_revision: Union[str, None] = "20261011_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = getLogger("alembic.runtime.migration")


def upgrade() -> None:
    op.create_table(
        "memory_chunks",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("memory_id", sa.String(length=80), nullable=False),
        sa.Column("source_id", sa.String(length=80), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("strategy", sa.String(length=32), nullable=False),
        sa.Column("strategy_version", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.current_timestamp(), nullable=False),
        sa.ForeignKeyConstraint(["memory_id"], ["memories.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_memory_chunks_memory_id_index", "memory_chunks", ["memory_id", "chunk_index"]
    )
    op.create_index("ix_memory_chunks_source_id", "memory_chunks", ["source_id"])

    connection = op.get_bind()
    try:
        connection.exec_driver_sql(
            "CREATE VIRTUAL TABLE chunk_fts USING fts5("
            "chunk_id UNINDEXED, memory_id UNINDEXED, source_id UNINDEXED, "
            "title, content, tokenize='unicode61 remove_diacritics 2')"
        )
    except OperationalError:
        logger.warning("SQLite FTS5 unavailable; chunk keyword search needs LIKE path")
        return

    connection.exec_driver_sql(
        "CREATE TRIGGER chunk_fts_insert AFTER INSERT ON memory_chunks BEGIN "
        "INSERT INTO chunk_fts(chunk_id, memory_id, source_id, title, content) "
        "SELECT new.id, new.memory_id, coalesce(new.source_id, ''), "
        "memories.title, new.chunk_text FROM memories "
        "WHERE memories.id = new.memory_id; END"
    )
    connection.exec_driver_sql(
        "CREATE TRIGGER chunk_fts_update AFTER UPDATE OF chunk_text ON memory_chunks BEGIN "
        "DELETE FROM chunk_fts WHERE chunk_id = old.id; "
        "INSERT INTO chunk_fts(chunk_id, memory_id, source_id, title, content) "
        "SELECT new.id, new.memory_id, coalesce(new.source_id, ''), "
        "memories.title, new.chunk_text FROM memories "
        "WHERE memories.id = new.memory_id; END"
    )
    connection.exec_driver_sql(
        "CREATE TRIGGER chunk_fts_delete AFTER DELETE ON memory_chunks BEGIN "
        "DELETE FROM chunk_fts WHERE chunk_id = old.id; END"
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql("DROP TRIGGER IF EXISTS chunk_fts_delete")
    connection.exec_driver_sql("DROP TRIGGER IF EXISTS chunk_fts_update")
    connection.exec_driver_sql("DROP TRIGGER IF EXISTS chunk_fts_insert")
    connection.exec_driver_sql("DROP TABLE IF EXISTS chunk_fts")
    op.drop_index("ix_memory_chunks_source_id", table_name="memory_chunks")
    op.drop_index("ix_memory_chunks_memory_id_index", table_name="memory_chunks")
    op.drop_table("memory_chunks")
