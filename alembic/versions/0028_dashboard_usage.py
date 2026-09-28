"""Named daily command counts and visible AI replies for the owner dashboard."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0028_dashboard_usage'
down_revision = '0027_ai_budget'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('guild_usage', sa.Column('command_counts', postgresql.JSONB(),
                  nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column('request_logs', sa.Column('response', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('request_logs', 'response')
    op.drop_column('guild_usage', 'command_counts')
