"""Daily usage and per-server chat allowances."""

from alembic import op
import sqlalchemy as sa

revision = "0016_usage_dashboard"
down_revision = "0015_add_autoresponder"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "guild_settings",
        sa.Column("daily_chat_limit", sa.Integer(), nullable=False, server_default="40"),
    )
    op.create_table(
        "guild_usage",
        sa.Column("guild_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("chats", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("commands", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_table("guild_usage")
    op.drop_column("guild_settings", "daily_chat_limit")
