"""Add soul enhancement and resumable dungeon; existing identities stay intact."""

from alembic import op
import sqlalchemy as sa

revision = "0032_fantasy_dungeon"
down_revision = "0031_fantasy_rebirth"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("fantasy_profiles", sa.Column("weapon_level", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("fantasy_profiles", sa.Column("highest_floor", sa.Integer(), nullable=False, server_default="0"))
    op.create_check_constraint("ck_fantasy_campaign", "fantasy_profiles", "weapon_level >= 0 AND weapon_level <= 10 AND highest_floor >= 0 AND highest_floor <= 10")
    op.create_table(
        "fantasy_dungeon_runs",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("fantasy_profiles.user_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("token", sa.String(32), nullable=False),
        sa.Column("floor", sa.Integer(), nullable=False),
        sa.Column("encounter", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("phase", sa.String(20), nullable=False),
        sa.Column("hp", sa.Integer(), nullable=False),
        sa.Column("mp", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("floor BETWEEN 1 AND 10 AND encounter BETWEEN 0 AND 3", name="ck_dungeon_position"),
        sa.CheckConstraint("hp >= 0 AND mp >= 0 AND revision >= 0", name="ck_dungeon_resources"),
        sa.CheckConstraint("phase IN ('intro','combat','victory','story','boss_intro','cleared','seal','defeated','complete','abandoned')", name="ck_dungeon_phase"),
    )


def downgrade():
    op.drop_table("fantasy_dungeon_runs")
    op.drop_constraint("ck_fantasy_campaign", "fantasy_profiles", type_="check")
    op.drop_column("fantasy_profiles", "highest_floor")
    op.drop_column("fantasy_profiles", "weapon_level")
