"""add structured Memory System v2 fields

Revision ID: 0008_add_memory_v2
Revises: 0007_add_server_lore
Create Date: 2026-08-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0008_add_memory_v2"
down_revision = "0007_add_server_lore"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("bot_memories")}

    if "category" not in columns:
        op.add_column(
            "bot_memories",
            sa.Column(
                "category",
                sa.String(length=32),
                server_default="personal",
                nullable=False,
            ),
        )
    if "memory_key" not in columns:
        op.add_column(
            "bot_memories",
            sa.Column("memory_key", sa.String(length=80), nullable=True),
        )
    if "updated_at" not in columns:
        op.add_column(
            "bot_memories",
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )

    op.execute(
        sa.text(
            "UPDATE bot_memories "
            "SET memory_key = 'legacy_' || id::text "
            "WHERE memory_key IS NULL OR memory_key = ''"
        )
    )
    op.alter_column("bot_memories", "memory_key", nullable=False)

    inspector = sa.inspect(op.get_bind())
    constraint_names = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("bot_memories")
    }
    if "uq_bot_memories_identity_key" not in constraint_names:
        op.create_unique_constraint(
            "uq_bot_memories_identity_key",
            "bot_memories",
            ["guild_id", "source_user_id", "category", "memory_key"],
        )


def downgrade() -> None:
    op.drop_constraint(
        "uq_bot_memories_identity_key",
        "bot_memories",
        type_="unique",
    )
    op.drop_column("bot_memories", "updated_at")
    op.drop_column("bot_memories", "memory_key")
    op.drop_column("bot_memories", "category")
