"""add shared server lore

Revision ID: 0007_add_server_lore
Revises: 0006_add_meyaya_decay_clocks
Create Date: 2026-08-27
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007_add_server_lore"
down_revision = "0006_add_meyaya_decay_clocks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("server_lore"):
        return

    op.create_table(
        "server_lore",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("normalized_key", sa.String(length=255), nullable=False),
        sa.Column("source_channel_id", sa.BigInteger(), nullable=True),
        sa.Column("source_message_id", sa.BigInteger(), nullable=True),
        sa.Column("source_user_id", sa.BigInteger(), nullable=True),
        sa.Column("times_seen", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("guild_id", "normalized_key", name="uq_server_lore_guild_key"),
    )
    op.create_index("ix_server_lore_guild_id", "server_lore", ["guild_id"])


def downgrade() -> None:
    op.drop_index("ix_server_lore_guild_id", table_name="server_lore")
    op.drop_table("server_lore")
