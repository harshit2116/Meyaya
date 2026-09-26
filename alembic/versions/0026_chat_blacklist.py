"""Persist server-specific Meyaya access restrictions."""

from alembic import op
import sqlalchemy as sa

revision = "0026_chat_blacklist"
down_revision = "0025_nickname_controls"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chat_blacklist",
        sa.Column("guild_id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), primary_key=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(300), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("actor_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade():
    op.drop_table("chat_blacklist")
