"""Widen fantasy_duel_results.rounds constraint to cover full duel and dungeon lengths."""

from alembic import op

revision = "0043_widen_duel_rounds"
down_revision = "0042_conversation_outcomes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_duel_rounds", "fantasy_duel_results", type_="check")
    op.create_check_constraint(
        "ck_duel_rounds",
        "fantasy_duel_results",
        "rounds BETWEEN 1 AND 60",
    )


def downgrade() -> None:
    op.drop_constraint("ck_duel_rounds", "fantasy_duel_results", type_="check")
    op.execute("UPDATE fantasy_duel_results SET rounds = 6 WHERE rounds > 6")
    op.create_check_constraint(
        "ck_duel_rounds",
        "fantasy_duel_results",
        "rounds BETWEEN 1 AND 6",
    )
