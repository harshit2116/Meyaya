"""Persist the per-server automatic reply setting."""

from alembic import op
import sqlalchemy as sa

revision = "0015_add_autoresponder"
down_revision = "0014_add_guild_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "guild_settings",
        sa.Column("autoresponder_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("guild_settings", "autoresponder_enabled")
