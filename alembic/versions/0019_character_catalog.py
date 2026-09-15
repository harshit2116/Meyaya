"""Provider-reviewed character catalog."""

from alembic import op
import sqlalchemy as sa

revision = "0019_character_catalog"
down_revision = "0018_moderation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "catalog_policies",
        sa.Column("provider", sa.String(40), primary_key=True),
        sa.Column("metadata_allowed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("remote_images_allowed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("evidence", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "reviewed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "catalog_characters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("gender", sa.String(40), nullable=True),
        sa.Column("series", sa.JSON(), nullable=False),
        sa.Column("source_provider", sa.String(40), nullable=False),
        sa.Column("source_character_id", sa.String(80), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("rarity", sa.Integer(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("popularity", sa.Integer(), nullable=True),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("takedown_reason", sa.Text(), nullable=True),
        sa.Column(
            "fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("source_provider", "source_character_id"),
    )
    op.create_table(
        "catalog_images",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "character_id",
            sa.Integer(),
            sa.ForeignKey("catalog_characters.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("source_provider", sa.String(40), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("image_source_url", sa.Text(), nullable=False),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("takedown_reason", sa.Text(), nullable=True),
    )
    op.create_table(
        "catalog_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("target", sa.String(100), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade():
    for name in ("catalog_audit", "catalog_images", "catalog_characters", "catalog_policies"):
        op.drop_table(name)
