"""Durable server voice hours."""
from alembic import op
import sqlalchemy as sa
revision = '0036_voice_usage'
down_revision = '0035_dashboard_history'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('guild_voice_usage',
        sa.Column('session_id', sa.String(36), primary_key=True),
        sa.Column('day', sa.Date(), primary_key=True),
        sa.Column('guild_id', sa.BigInteger(), nullable=False),
        sa.Column('seconds', sa.Float(), nullable=False))
    op.create_index('ix_guild_voice_usage_guild_id', 'guild_voice_usage', ['guild_id'])


def downgrade():
    op.drop_table('guild_voice_usage')
