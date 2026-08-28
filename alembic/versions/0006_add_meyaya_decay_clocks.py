"""add independent Meyaya state decay clocks

Revision ID: 0006_add_meyaya_decay_clocks
Revises: 0005_add_meyaya_system
Create Date: 2026-08-27
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_add_meyaya_decay_clocks"
down_revision = "0005_add_meyaya_system"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    global_columns = {
        column["name"] for column in inspector.get_columns("meyaya_global_states")
    }
    user_columns = {
        column["name"] for column in inspector.get_columns("meyaya_user_states")
    }

    for column_name in (
        "mood_changed_at",
        "energy_updated_at",
        "annoyance_updated_at",
    ):
        if column_name not in global_columns:
            op.add_column(
                "meyaya_global_states",
                sa.Column(
                    column_name,
                    sa.DateTime(timezone=True),
                    server_default=sa.func.now(),
                    nullable=False,
                ),
            )

    if "annoyance_updated_at" not in user_columns:
        op.add_column(
            "meyaya_user_states",
            sa.Column(
                "annoyance_updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )


def downgrade() -> None:
    op.drop_column("meyaya_user_states", "annoyance_updated_at")
    op.drop_column("meyaya_global_states", "annoyance_updated_at")
    op.drop_column("meyaya_global_states", "energy_updated_at")
    op.drop_column("meyaya_global_states", "mood_changed_at")
