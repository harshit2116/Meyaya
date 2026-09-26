"""Allow servers to bind conversational replies to one channel."""

from alembic import op
import sqlalchemy as sa

revision = "0024_chat_channel"
down_revision = "0023_creative_nicknames"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("guild_settings", sa.Column("chat_channel_id", sa.BigInteger(), nullable=True))


def downgrade():
    op.drop_column("guild_settings", "chat_channel_id")
