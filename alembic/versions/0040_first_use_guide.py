"""Remember the first-use guide without interrupting established conversations."""

import sqlalchemy as sa

from alembic import op

revision = "0040_first_use_guide"
down_revision = "0039_topgg_auto_detection"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "first_use_guides",
        sa.Column("user_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column(
            "shown_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("claim_token", sa.String(32)),
    )
    # Existing conversation participants can reopen /guide whenever they want.
    # Only IDs and timestamps are copied, never messages or remembered facts.
    op.execute(sa.text("""
        INSERT INTO first_use_guides (user_id, shown_at)
        SELECT user_id, CURRENT_TIMESTAMP FROM (
            SELECT user_id FROM request_logs WHERE kind = 'chat'
            UNION
            SELECT user_id FROM meyaya_user_states WHERE last_interaction_at IS NOT NULL
        ) AS existing_members
        WHERE user_id > 0
        ON CONFLICT (user_id) DO NOTHING
    """))


def downgrade():
    op.drop_table("first_use_guides")
