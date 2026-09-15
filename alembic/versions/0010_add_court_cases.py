"""add persistent court cases

Revision ID: 0010_add_court_cases
Revises: 0009_align_query_indexes
Create Date: 2026-08-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0010_add_court_cases"
down_revision = "0009_align_query_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "court_cases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("plaintiff_id", sa.BigInteger(), nullable=False),
        sa.Column("defendant_id", sa.BigInteger(), nullable=False),
        sa.Column("charge", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("plaintiff_statement", sa.Text(), nullable=True),
        sa.Column("defendant_statement", sa.Text(), nullable=True),
        sa.Column(
            "witness_statements", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False
        ),
        sa.Column("verdict", sa.String(length=32), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("punishment", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_court_cases_guild_id", "court_cases", ["guild_id"])
    op.create_index("ix_court_cases_plaintiff_id", "court_cases", ["plaintiff_id"])
    op.create_index("ix_court_cases_defendant_id", "court_cases", ["defendant_id"])
    op.create_index("ix_court_cases_status", "court_cases", ["status"])


def downgrade() -> None:
    op.drop_index("ix_court_cases_status", table_name="court_cases")
    op.drop_index("ix_court_cases_defendant_id", table_name="court_cases")
    op.drop_index("ix_court_cases_plaintiff_id", table_name="court_cases")
    op.drop_index("ix_court_cases_guild_id", table_name="court_cases")
    op.drop_table("court_cases")
