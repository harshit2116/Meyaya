"""Permanent global fantasy identities with stored generation snapshots."""

from alembic import op
import sqlalchemy as sa

revision = "0029_fantasy_profiles"
down_revision = "0028_dashboard_usage"
branch_labels = None
depends_on = None


def upgrade():
    columns = [
        sa.Column("user_id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column("generation_version", sa.Integer(), nullable=False),
    ]
    for name, length in (
        ("class_id", 40),
        ("class_name", 80),
        ("subclass_id", 80),
        ("subclass_name", 80),
        ("affinity_id", 30),
        ("affinity_name", 40),
        ("weapon_id", 120),
        ("weapon_name", 100),
        ("weapon_family", 30),
        ("weapon_type", 50),
        ("weapon_rarity", 30),
        ("weapon_trait", 200),
        ("passive_id", 80),
        ("passive_name", 100),
        ("signature_id", 80),
        ("signature_name", 100),
        ("fantasy_title", 150),
        ("alignment", 40),
        ("meyaya_reaction", 240),
    ):
        columns.append(sa.Column(name, sa.String(length), nullable=False))
    for name in (
        "level",
        "hp",
        "max_hp",
        "mp",
        "max_mp",
        "strength",
        "dexterity",
        "intelligence",
        "vitality",
        "luck",
    ):
        columns.append(sa.Column(name, sa.Integer(), nullable=False))
    columns.extend(
        [
            sa.Column("xp", sa.BigInteger(), nullable=False),
            sa.Column("base_stats", sa.JSON(), nullable=False),
            sa.Column(
                "awakened_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        ]
    )
    for name in ("weapon_lore", "passive_description", "signature_description", "description"):
        columns.append(sa.Column(name, sa.Text(), nullable=False))
    op.create_table(
        "fantasy_profiles",
        *columns,
        sa.CheckConstraint("user_id > 0", name="ck_fantasy_user"),
        sa.CheckConstraint("level >= 1 AND xp >= 0", name="ck_fantasy_progression"),
        sa.CheckConstraint(
            "max_hp > 0 AND hp >= 0 AND hp <= max_hp AND max_mp > 0 AND mp >= 0 AND mp <= max_mp",
            name="ck_fantasy_resources",
        ),
        sa.CheckConstraint(
            "strength > 0 AND dexterity > 0 AND intelligence > 0 AND vitality > 0 AND luck > 0",
            name="ck_fantasy_stats",
        ),
        sa.CheckConstraint("generation_version >= 1", name="ck_fantasy_version"),
    )


def downgrade():
    op.drop_table("fantasy_profiles")
