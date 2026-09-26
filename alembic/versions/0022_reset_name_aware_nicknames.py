"""Clear generic nicknames before enabling name-aware assignment.

Revision ID: 0022_name_aware_nicknames
Revises: 0021_gameplay_summons
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0022_name_aware_nicknames"
down_revision = "0021_gameplay_summons"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This intentionally preserves every relationship score and timestamp.
    op.execute(sa.text("UPDATE meyaya_user_states SET nickname = NULL WHERE nickname IS NOT NULL"))


def downgrade() -> None:
    # Cleared generated nicknames cannot be reconstructed reliably.
    pass
