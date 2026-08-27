"""add context fields to bot memories

Revision ID: 0004_add_memory_context
Revises: 0003_add_bot_memories
Create Date: 2026-08-25
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_add_memory_context"
down_revision = "0003_add_bot_memories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add source context to permanent memories."""

    op.add_column("bot_memories", sa.Column("channel_id", sa.BigInteger(), nullable=True))
    op.add_column("bot_memories", sa.Column("source_message_id", sa.BigInteger(), nullable=True))
    op.add_column("bot_memories", sa.Column("source_user_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "bot_memories", sa.Column("source_user_name", sa.String(length=100), nullable=True)
    )
    op.add_column("bot_memories", sa.Column("conversation_summary", sa.Text(), nullable=True))
    op.create_index("ix_bot_memories_channel_id", "bot_memories", ["channel_id"])
    op.create_index("ix_bot_memories_source_message_id", "bot_memories", ["source_message_id"])
    op.create_index("ix_bot_memories_source_user_id", "bot_memories", ["source_user_id"])


def downgrade() -> None:
    """Remove source context from permanent memories."""

    op.drop_index("ix_bot_memories_source_user_id", table_name="bot_memories")
    op.drop_index("ix_bot_memories_source_message_id", table_name="bot_memories")
    op.drop_index("ix_bot_memories_channel_id", table_name="bot_memories")
    op.drop_column("bot_memories", "conversation_summary")
    op.drop_column("bot_memories", "source_user_name")
    op.drop_column("bot_memories", "source_user_id")
    op.drop_column("bot_memories", "source_message_id")
    op.drop_column("bot_memories", "channel_id")
