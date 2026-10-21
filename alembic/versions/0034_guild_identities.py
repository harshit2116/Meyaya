"""Retain server and owner names independently of bot membership."""
from alembic import op
import sqlalchemy as sa

revision = '0034_guild_identities'
down_revision = '0033_fantasy_worldline'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('guild_identities',
        sa.Column('guild_id', sa.BigInteger(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('owner_id', sa.BigInteger(), nullable=True),
        sa.Column('owner_name', sa.String(100), nullable=True),
        sa.Column('icon_url', sa.String(512), nullable=True))


def downgrade():
    op.drop_table('guild_identities')
