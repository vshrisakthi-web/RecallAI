"""Create the structured memory schema and optional FTS5 index."""

from __future__ import annotations

from logging import getLogger
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.exc import OperationalError

revision: str = "20261011_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = getLogger("alembic.runtime.migration")


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("identity_key", sa.String(length=2200), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("canonical_source_url", sa.String(length=2048), nullable=True),
        sa.Column("domain", sa.String(length=253), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False),
        sa.UniqueConstraint("identity_key", name="uq_sources_identity_key"),
    )
    op.create_index("ix_sources_domain", "sources", ["domain"])
    op.create_index("ix_sources_type_domain", "sources", ["source_type", "domain"])

    op.create_table(
        "memories",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("source_id", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("normalized_content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("dedup_key", sa.String(length=2400), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("capture_type", sa.String(length=32), nullable=True),
        sa.Column("selected_text", sa.Text(), nullable=True),
        sa.Column("surrounding_context", sa.Text(), nullable=True),
        sa.Column("extraction_status", sa.String(length=32), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("record_metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("dedup_key", name="uq_memories_dedup_key"),
    )
    op.create_index("ix_memories_source_id", "memories", ["source_id"])
    op.create_index("ix_memories_captured_at_id", "memories", ["captured_at", "id"])
    op.create_index("ix_memories_content_hash", "memories", ["content_hash"])

    op.create_table(
        "conversations",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("title", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False),
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("input_reference", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False),
    )

    connection = op.get_bind()
    try:
        connection.exec_driver_sql(
            "CREATE VIRTUAL TABLE memories_fts USING fts5("
            "memory_id UNINDEXED, source_id UNINDEXED, title, content, source_title, domain, "
            "tokenize='unicode61 remove_diacritics 2')"
        )
    except OperationalError:
        logger.warning("SQLite FTS5 unavailable; memory search will use LIKE fallback")
        return

    connection.exec_driver_sql(
        "CREATE TRIGGER memories_fts_insert AFTER INSERT ON memories BEGIN "
            "INSERT INTO memories_fts(memory_id, source_id, title, content, source_title, domain) "
            "SELECT new.id, sources.id, new.title, new.normalized_content, sources.title, "
        "coalesce(sources.domain, '') FROM sources WHERE sources.id = new.source_id; "
        "END"
    )
    connection.exec_driver_sql(
        "CREATE TRIGGER memories_fts_update AFTER UPDATE ON memories BEGIN "
        "DELETE FROM memories_fts WHERE memory_id = old.id; "
        "INSERT INTO memories_fts(memory_id, source_id, title, content, source_title, domain) "
        "SELECT new.id, sources.id, new.title, new.normalized_content, sources.title, "
        "coalesce(sources.domain, '') FROM sources WHERE sources.id = new.source_id; "
        "END"
    )
    connection.exec_driver_sql(
        "CREATE TRIGGER memories_fts_delete AFTER DELETE ON memories BEGIN "
        "DELETE FROM memories_fts WHERE memory_id = old.id; END"
    )
    connection.exec_driver_sql(
        "CREATE TRIGGER sources_fts_update AFTER UPDATE OF title, domain ON sources BEGIN "
        "UPDATE memories_fts SET source_title = new.title, "
        "domain = coalesce(new.domain, '') WHERE source_id = new.id; END"
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql("DROP TRIGGER IF EXISTS sources_fts_update")
    connection.exec_driver_sql("DROP TRIGGER IF EXISTS memories_fts_delete")
    connection.exec_driver_sql("DROP TRIGGER IF EXISTS memories_fts_update")
    connection.exec_driver_sql("DROP TRIGGER IF EXISTS memories_fts_insert")
    connection.exec_driver_sql("DROP TABLE IF EXISTS memories_fts")
    op.drop_table("tasks")
    op.drop_table("conversations")
    op.drop_index("ix_memories_content_hash", table_name="memories")
    op.drop_index("ix_memories_captured_at_id", table_name="memories")
    op.drop_index("ix_memories_source_id", table_name="memories")
    op.drop_table("memories")
    op.drop_index("ix_sources_type_domain", table_name="sources")
    op.drop_index("ix_sources_domain", table_name="sources")
    op.drop_table("sources")
