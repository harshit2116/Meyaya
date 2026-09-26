"""Store members' nickname preferences without resetting existing names."""

from alembic import op
import sqlalchemy as sa

revision = "0025_nickname_controls"
down_revision = "0024_chat_channel"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "meyaya_user_states",
        sa.Column("nickname_mode", sa.String(12), nullable=False, server_default="auto"),
    )
    op.add_column(
        "meyaya_user_states",
        sa.Column("nickname_revision", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("meyaya_user_states", "nickname_revision")
    op.drop_column("meyaya_user_states", "nickname_mode")
