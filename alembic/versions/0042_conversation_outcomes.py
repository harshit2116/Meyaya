"""Track conversation outcomes and voice coverage without retaining transcripts."""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = '0042_conversation_outcomes'
down_revision = '0041_voice_summaries'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('request_logs', sa.Column('outcome', sa.String(32)))
    op.add_column('request_logs', sa.Column('latency_ms', sa.Integer()))
    op.add_column('voice_summaries', sa.Column('coverage_reasons', postgresql.JSONB(), nullable=False, server_default='[]'))
    op.add_column('voice_summaries', sa.Column('end_reason', sa.String(32)))


def downgrade():
    op.drop_column('voice_summaries', 'end_reason')
    op.drop_column('voice_summaries', 'coverage_reasons')
    op.drop_column('request_logs', 'latency_ms')
    op.drop_column('request_logs', 'outcome')
