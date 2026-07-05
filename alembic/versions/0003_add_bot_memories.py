"""add bot_memories table

Revision ID: 0003_add_bot_memories
Revises: 0002_add_marriages
Create Date: 2026-07-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_add_bot_memories"
down_revision = "0002_add_marriages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the bot_memories table."""

    op.create_table(
        "bot_memories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("guild_id", sa.BigInteger(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_bot_memories_guild_id", "bot_memories", ["guild_id"])


def downgrade() -> None:
    """Drop the bot_memories table."""

    op.drop_index("ix_bot_memories_guild_id", table_name="bot_memories")
    op.drop_table("bot_memories")