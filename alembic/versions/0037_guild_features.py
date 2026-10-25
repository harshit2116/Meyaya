"""Per-server Meyaya feature switches, enabled by default."""
from alembic import op
import sqlalchemy as sa

revision = "0037_guild_features"
down_revision = "0036_voice_usage"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("guild_settings", sa.Column("disabled_features", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("guild_usage", sa.Column("reset_generation", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("guild_usage", "reset_generation")
    op.drop_column("guild_settings", "disabled_features")
