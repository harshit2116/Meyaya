"""add marriages table

Revision ID: 0002_add_marriages
Revises: 0001_initial_schema
Create Date: 2026-07-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_add_marriages"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the marriages table."""

    op.create_table(
        "marriages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_a_id", sa.BigInteger(), nullable=False),
        sa.Column("user_b_id", sa.BigInteger(), nullable=False),
        sa.Column("married_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("user_a_id", "user_b_id", name="uq_marriage_pair"),
    )
    op.create_index("ix_marriages_user_a_id", "marriages", ["user_a_id"])
    op.create_index("ix_marriages_user_b_id", "marriages", ["user_b_id"])


def downgrade() -> None:
    """Drop the marriages table."""

    op.drop_index("ix_marriages_user_b_id", table_name="marriages")
    op.drop_index("ix_marriages_user_a_id", table_name="marriages")
    op.drop_table("marriages")