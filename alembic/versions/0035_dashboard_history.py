"""Server membership history and dashboard settings audit."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = '0035_dashboard_history'
down_revision = '0034_guild_identities'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('guild_identities', sa.Column('is_current', sa.Boolean(), nullable=True))
    for name in ('joined_at', 'left_at', 'last_activity_at'):
        op.add_column('guild_identities', sa.Column(name, sa.DateTime(timezone=True), nullable=True))
    op.create_table('guild_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('guild_id', sa.BigInteger(), nullable=False),
        sa.Column('event_type', sa.String(32), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('actor', sa.String(80), nullable=True),
        sa.Column('details', postgresql.JSONB(), nullable=False))
    op.create_index('ix_guild_events_guild_id', 'guild_events', ['guild_id'])


def downgrade():
    op.drop_table('guild_events')
    for name in ('is_current', 'joined_at', 'left_at', 'last_activity_at'):
        op.drop_column('guild_identities', name)
