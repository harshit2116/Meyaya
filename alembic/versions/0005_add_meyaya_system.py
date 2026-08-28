"""add Meyaya mood and relationship state

Revision ID: 0005_add_meyaya_system
Revises: 0004_add_memory_context
Create Date: 2026-08-27
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_add_meyaya_system"
down_revision = "0004_add_memory_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meyaya_global_states",
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("mood", sa.String(length=24), server_default="normal", nullable=False),
        sa.Column("energy", sa.Integer(), server_default=sa.text("70"), nullable=False),
        sa.Column("annoyance", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("mood_reason", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("guild_id"),
    )
    op.create_table(
        "meyaya_user_states",
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("familiarity", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("affection", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("annoyance", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("nickname", sa.String(length=80), nullable=True),
        sa.Column("last_interaction_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("guild_id", "user_id"),
    )
    op.create_index("ix_meyaya_user_states_user_id", "meyaya_user_states", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_meyaya_user_states_user_id", table_name="meyaya_user_states")
    op.drop_table("meyaya_user_states")
    op.drop_table("meyaya_global_states")
