"""Compact duel history, separate from permanent awakened identities."""

from alembic import op
import sqlalchemy as sa

revision = "0030_fantasy_duels"
down_revision = "0029_fantasy_profiles"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "fantasy_duel_results",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("challenger_id", sa.BigInteger(), nullable=False),
        sa.Column("opponent_id", sa.BigInteger(), nullable=False),
        sa.Column("winner_id", sa.BigInteger()),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("rules_version", sa.Integer(), nullable=False),
        sa.Column("rounds", sa.Integer(), nullable=False),
        sa.Column("arena", sa.String(60), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("challenger_id <> opponent_id", name="ck_duel_distinct"),
        sa.CheckConstraint("rounds BETWEEN 1 AND 6", name="ck_duel_rounds"),
        sa.CheckConstraint(
            "winner_id IS NULL OR winner_id IN (challenger_id, opponent_id)", name="ck_duel_winner"
        ),
    )
    op.create_index(
        "ix_duel_challenger_time", "fantasy_duel_results", ["challenger_id", "created_at"]
    )
    op.create_index("ix_duel_opponent_time", "fantasy_duel_results", ["opponent_id", "created_at"])


def downgrade():
    op.drop_table("fantasy_duel_results")
