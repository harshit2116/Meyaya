"""Retain short voice-session summaries for owner review."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0041_voice_summaries"
down_revision = "0040_first_use_guide"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "voice_summaries",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("session_id", sa.String(36), nullable=False, unique=True),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_name", sa.String(100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("participants", postgresql.JSONB(), nullable=False),
        sa.Column("summary", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("partial", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_voice_summaries_guild_id", "voice_summaries", ["guild_id", "id"])
    op.create_index("ix_voice_summaries_ended_at", "voice_summaries", ["ended_at"])


def downgrade():
    op.drop_table("voice_summaries")
