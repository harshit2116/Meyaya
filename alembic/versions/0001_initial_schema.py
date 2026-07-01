"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the initial Meyaya tables."""

    op.create_table(
        "users",
        sa.Column("user_id", sa.BigInteger(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "user_statistics",
        sa.Column("user_id", sa.BigInteger(), primary_key=True),
        sa.Column("total_given", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hugs_given", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hugs_received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kisses_given", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kisses_received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pats_given", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pats_received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_interactions", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "relationship_interactions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_a_id", sa.BigInteger(), nullable=False),
        sa.Column("user_b_id", sa.BigInteger(), nullable=False),
        sa.Column("interaction_type", sa.String(length=32), nullable=False),
        sa.Column("interaction_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_interaction_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("user_a_id", "user_b_id", "interaction_type", name="uq_relationship_type"),
    )
    op.create_table(
        "daily_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("dumbest_member_id", sa.BigInteger(), nullable=True),
        sa.Column("smartest_member_id", sa.BigInteger(), nullable=True),
        sa.Column("clown_member_id", sa.BigInteger(), nullable=True),
        sa.Column("iq_seed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("guild_id", "day", name="uq_daily_result_day"),
    )


def downgrade() -> None:
    """Drop the initial Meyaya tables."""

    op.drop_table("daily_results")
    op.drop_table("relationship_interactions")
    op.drop_table("user_statistics")
    op.drop_table("users")
