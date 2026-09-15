"""add durable per-server settings

Revision ID: 0014_add_guild_settings
Revises: 0013_complete_memory_v2
Create Date: 2026-09-14
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0014_add_guild_settings"
down_revision = "0013_complete_memory_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guild_settings",
        sa.Column("guild_id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "command_prefix",
            sa.String(length=10),
            server_default="uwu",
            nullable=False,
        ),
        sa.Column("updated_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("guild_settings")
