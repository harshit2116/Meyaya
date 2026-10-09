"""Permanent Memory World choice; preserve all existing soul progression."""
from alembic import op
import sqlalchemy as sa

revision = "0033_fantasy_worldline"
down_revision = "0032_fantasy_dungeon"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("fantasy_profiles", sa.Column("ending_route", sa.String(10), nullable=True))
    op.add_column("fantasy_profiles", sa.Column("ending_chosen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("fantasy_profiles", sa.Column("ending_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint("ck_fantasy_worldline", "fantasy_profiles", "ending_route IS NULL OR ending_route IN ('meyaya','veyra')")
    # Old Floor 10 was a player battle and had no explicit final choice. Let
    # those users see the new Core without taking XP or weapon upgrades away.
    op.execute("""UPDATE fantasy_dungeon_runs
        SET phase = 'seal', encounter = 0, revision = revision + 1,
            state = json_build_object('guild_id', COALESCE(state->'guild_id', '0'::json),
                                      'sequence', 'core', 'scene', 0, 'story_version', 2)
        WHERE floor = 10""")


def downgrade():
    op.drop_constraint("ck_fantasy_worldline", "fantasy_profiles", type_="check")
    op.drop_column("fantasy_profiles", "ending_completed_at")
    op.drop_column("fantasy_profiles", "ending_chosen_at")
    op.drop_column("fantasy_profiles", "ending_route")
