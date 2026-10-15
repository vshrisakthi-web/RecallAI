"""Persist embedding vectors for indexed chunks (Module 6, Task 6.3).

Additive only: ``memory_chunks`` and earlier tables are untouched. Vectors
are stored as little-endian float32 blobs with their model id and dimensions
so a model or dimension change is detectable (stale vectors are excluded
from search and reported for reindexing) instead of silently comparing
incompatible vectors. ``ON DELETE CASCADE`` on both foreign keys means
deleting a memory purges its chunks and their vectors with no extra code —
the FK pragma is enabled in ``app.database.session``.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261011_0003"
down_revision: Union[str, None] = "20261011_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chunk_embeddings",
        sa.Column("chunk_id", sa.String(length=80), primary_key=True),
        sa.Column("memory_id", sa.String(length=80), nullable=False, index=True),
        sa.Column("vector", sa.LargeBinary(), nullable=False),
        sa.Column("dims", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.current_timestamp(), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["memory_chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["memory_id"], ["memories.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("chunk_embeddings")
