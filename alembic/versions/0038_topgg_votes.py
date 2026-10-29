"""Durable Top.gg vote rewards and separate bonus reply accounting."""

import sqlalchemy as sa

from alembic import op

revision = "0038_topgg_votes"
down_revision = "0037_guild_features"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "topgg_votes",
        sa.Column("vote_id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("voted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("used", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("user_id", "voted_at", name="uq_topgg_user_vote_time"),
        sa.CheckConstraint("used >= 0 AND used <= credits", name="ck_topgg_vote_credits"),
        sa.CheckConstraint("credits = 20", name="ck_topgg_vote_reward"),
    )
    op.create_index("ix_topgg_votes_user_expiry", "topgg_votes", ["user_id", "expires_at"])
    op.add_column(
        "guild_usage", sa.Column("bonus_chats", sa.Integer(), nullable=False, server_default="0")
    )


def downgrade():
    op.drop_column("guild_usage", "bonus_chats")
    op.drop_index("ix_topgg_votes_user_expiry", table_name="topgg_votes")
    op.drop_table("topgg_votes")
