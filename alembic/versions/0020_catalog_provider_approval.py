"""Make provider approval sufficient for normal catalog imports."""

from alembic import op
import sqlalchemy as sa

revision = "0020_catalog_provider_approval"
down_revision = "0019_character_catalog"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "catalog_characters",
        sa.Column("review_required", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("catalog_characters", "review_required")
