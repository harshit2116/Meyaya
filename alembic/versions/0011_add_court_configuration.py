"""add per-server court channel configuration

Revision ID: 0011_add_court_configuration
Revises: 0010_add_court_cases
Create Date: 2026-08-29
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0011_add_court_configuration"
down_revision = "0010_add_court_cases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "court_configurations",
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_id", sa.BigInteger(), nullable=True),
        sa.Column("updated_by_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("guild_id"),
    )


def downgrade() -> None:
    op.drop_table("court_configurations")
