"""complete structured Memory System v2

Revision ID: 0013_complete_memory_v2
Revises: 0012_expand_court_workflow
Create Date: 2026-09-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0013_complete_memory_v2"
down_revision = "0012_expand_court_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Move legacy keyed memories into the complete structured lifecycle."""

    op.drop_constraint("uq_bot_memories_identity_key", "bot_memories", type_="unique")
    op.drop_index("ix_bot_memories_source_user_id", table_name="bot_memories")

    op.alter_column("bot_memories", "source_user_id", new_column_name="user_id")
    op.alter_column("bot_memories", "memory_key", new_column_name="relation")
    op.alter_column("bot_memories", "content", new_column_name="value")
    # Very old pre-context rows had no owner. Keep them migrated but isolated
    # under the non-Discord sentinel account instead of assigning them to a member.
    op.execute(sa.text("UPDATE bot_memories SET user_id = 0 WHERE user_id IS NULL"))
    op.alter_column("bot_memories", "user_id", nullable=False)

    op.add_column(
        "bot_memories",
        sa.Column("subject", sa.String(length=100), server_default="self", nullable=False),
    )
    op.add_column(
        "bot_memories",
        sa.Column("confidence", sa.Float(), server_default="0.8", nullable=False),
    )
    op.add_column(
        "bot_memories",
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
    )
    op.add_column("bot_memories", sa.Column("conflict_value", sa.Text(), nullable=True))
    op.add_column("bot_memories", sa.Column("conflict_confidence", sa.Float(), nullable=True))
    op.add_column(
        "bot_memories",
        sa.Column("conflict_source_message_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "bot_memories",
        sa.Column("lifecycle_reason", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "bot_memories",
        sa.Column(
            "last_confirmed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index("ix_bot_memories_user_id", "bot_memories", ["user_id"])
    op.create_index("ix_bot_memories_status", "bot_memories", ["status"])
    op.create_unique_constraint(
        "uq_bot_memories_identity_relation",
        "bot_memories",
        ["guild_id", "user_id", "category", "subject", "relation"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_bot_memories_identity_relation", "bot_memories", type_="unique")
    op.drop_index("ix_bot_memories_status", table_name="bot_memories")
    op.drop_index("ix_bot_memories_user_id", table_name="bot_memories")

    op.drop_column("bot_memories", "last_confirmed_at")
    op.drop_column("bot_memories", "lifecycle_reason")
    op.drop_column("bot_memories", "conflict_source_message_id")
    op.drop_column("bot_memories", "conflict_confidence")
    op.drop_column("bot_memories", "conflict_value")
    op.drop_column("bot_memories", "status")
    op.drop_column("bot_memories", "confidence")
    op.drop_column("bot_memories", "subject")

    op.alter_column("bot_memories", "value", new_column_name="content")
    op.alter_column("bot_memories", "relation", new_column_name="memory_key")
    op.alter_column("bot_memories", "user_id", new_column_name="source_user_id")
    op.alter_column("bot_memories", "source_user_id", nullable=True)
    op.create_index("ix_bot_memories_source_user_id", "bot_memories", ["source_user_id"])
    op.create_unique_constraint(
        "uq_bot_memories_identity_key",
        "bot_memories",
        ["guild_id", "source_user_id", "category", "memory_key"],
    )
