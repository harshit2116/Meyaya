"""Replace retained provider metadata with a gameplay-only summon roster."""

from alembic import op
import sqlalchemy as sa

revision = "0021_gameplay_summons"
down_revision = "0020_catalog_provider_approval"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "summon_characters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("provider_character_id", sa.String(80), nullable=False),
        sa.Column("rarity_stars", sa.Integer(), nullable=False),
        sa.Column("summon_weight", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("class_name", sa.String(80), nullable=False, server_default="Wanderer"),
        sa.Column("traits", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("passive", sa.String(250), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("image_disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("takedown_reason", sa.Text(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("provider", "provider_character_id"),
    )
    op.create_table(
        "catalog_provider_state",
        sa.Column("provider", sa.String(40), primary_key=True),
        sa.Column("blocked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    connection = op.get_bind()
    connection.execute(sa.text("""
            INSERT INTO summon_characters
              (provider, provider_character_id, rarity_stars, summon_weight, class_name,
               traits, passive, enabled, disabled, image_disabled, takedown_reason)
            SELECT source_provider, source_character_id,
                   LEAST(6, GREATEST(2, rarity)), 100, 'Wanderer', tags, '',
                   TRUE, disabled,
                   COALESCE((SELECT ci.disabled FROM catalog_images ci
                             WHERE ci.character_id = catalog_characters.id), FALSE),
                   takedown_reason
            FROM catalog_characters
            ON CONFLICT (provider, provider_character_id) DO NOTHING
            """))
    op.drop_table("catalog_images")
    op.drop_table("catalog_policies")
    op.drop_table("catalog_characters")


def downgrade():
    raise RuntimeError("Downgrade would recreate retained provider metadata")
