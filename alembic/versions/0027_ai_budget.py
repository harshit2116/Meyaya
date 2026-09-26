"""Durable emergency request and voice-minute budgets."""

from alembic import op
import sqlalchemy as sa

revision = "0027_ai_budget"
down_revision = "0026_chat_blacklist"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_budget",
        sa.Column("scope_id", sa.BigInteger(), primary_key=True),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("kind", sa.String(16), primary_key=True),
        sa.Column("used", sa.Integer(), nullable=False),
    )


def downgrade():
    op.drop_table("ai_budget")
