"""Resumable automatic vote detection and pending thank-you delivery."""

import sqlalchemy as sa

from alembic import op

revision = "0039_topgg_auto_detection"
down_revision = "0038_topgg_votes"
branch_labels = None
depends_on = None


def upgrade():
    # Existing receipts already had their one DM attempt in the manual flow.
    # Backfill those as attempted; new receipts start pending.
    op.add_column(
        "topgg_votes",
        sa.Column(
            "notify_attempted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_topgg_votes_pending_dm",
        "topgg_votes",
        ["voted_at"],
        postgresql_where=sa.text("notify_attempted_at IS NULL"),
    )
    op.create_table(
        "topgg_poll_state",
        sa.Column("project_id", sa.String(19), primary_key=True),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("scan_started_at", sa.DateTime(timezone=True)),
        sa.Column("scan_since_at", sa.DateTime(timezone=True)),
        sa.Column("cursor", sa.String(2048)),
        sa.Column("lease_owner", sa.String(32)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
    )


def downgrade():
    op.drop_table("topgg_poll_state")
    op.drop_index("ix_topgg_votes_pending_dm", table_name="topgg_votes")
    op.drop_column("topgg_votes", "notify_attempted_at")
