"""Persistent player rebirth count and cooldown; owner reset remains unrestricted."""

from alembic import op
import sqlalchemy as sa

revision = "0031_fantasy_rebirth"
down_revision = "0030_fantasy_duels"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "fantasy_profiles",
        sa.Column("rebirth_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "fantasy_profiles", sa.Column("last_rebirth_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade():
    op.drop_column("fantasy_profiles", "last_rebirth_at")
    op.drop_column("fantasy_profiles", "rebirth_count")
