"""expand court witnesses and clarification workflow

Revision ID: 0012_expand_court_workflow
Revises: 0011_add_court_configuration
Create Date: 2026-08-29
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0012_expand_court_workflow"
down_revision = "0011_add_court_configuration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "court_cases",
        sa.Column(
            "registered_witness_ids",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
    )
    op.add_column("court_cases", sa.Column("clarification_question", sa.Text(), nullable=True))
    op.add_column(
        "court_cases", sa.Column("clarification_target", sa.String(length=16), nullable=True)
    )
    op.add_column(
        "court_cases",
        sa.Column(
            "clarification_answers",
            sa.JSON(),
            server_default=sa.text("'{}'::json"),
            nullable=False,
        ),
    )
    op.add_column("court_cases", sa.Column("plaintiff_summary", sa.Text(), nullable=True))
    op.add_column("court_cases", sa.Column("defendant_summary", sa.Text(), nullable=True))
    op.add_column("court_cases", sa.Column("decisive_factors", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("court_cases", "decisive_factors")
    op.drop_column("court_cases", "defendant_summary")
    op.drop_column("court_cases", "plaintiff_summary")
    op.drop_column("court_cases", "clarification_answers")
    op.drop_column("court_cases", "clarification_target")
    op.drop_column("court_cases", "clarification_question")
    op.drop_column("court_cases", "registered_witness_ids")
