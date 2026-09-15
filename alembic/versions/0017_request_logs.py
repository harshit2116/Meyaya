"""Short-lived owner request review records."""

from alembic import op
import sqlalchemy as sa

revision = "0017_request_logs"
down_revision = "0016_usage_dashboard"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "request_logs",
        sa.Column("event_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("user_name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_request_logs_guild_event", "request_logs", ["guild_id", "event_id"])
    op.create_index("ix_request_logs_created_at", "request_logs", ["created_at"])


def downgrade():
    op.drop_table("request_logs")
