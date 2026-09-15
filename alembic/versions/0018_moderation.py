"""Moderation settings and reversible lockdowns."""

from alembic import op
import sqlalchemy as sa

revision = "0018_moderation"
down_revision = "0017_request_logs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "moderation_settings",
        sa.Column("guild_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        *[
            sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.true())
            for name in ("probation", "cross_spam", "anti_invite")
        ],
        sa.Column("raid_active", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "channel_locks",
        sa.Column("channel_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("single", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("raid", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("snapshot", sa.JSON(), nullable=False),
    )
    op.create_index("ix_channel_locks_guild_id", "channel_locks", ["guild_id"])


def downgrade():
    op.drop_table("channel_locks")
    op.drop_table("moderation_settings")
