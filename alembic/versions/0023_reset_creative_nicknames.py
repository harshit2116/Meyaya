"""Clear existing nicknames before enabling creative name-play assignment.

Revision ID: 0023_creative_nicknames
Revises: 0022_name_aware_nicknames
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0023_creative_nicknames"
down_revision = "0022_name_aware_nicknames"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep every relationship score and timestamp; only names are regenerated.
    op.execute(sa.text("UPDATE meyaya_user_states SET nickname = NULL WHERE nickname IS NOT NULL"))


def downgrade() -> None:
    # Generated nicknames cannot be reconstructed after they are cleared.
    pass
