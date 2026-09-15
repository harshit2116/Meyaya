"""align frequently queried model indexes

Revision ID: 0009_align_query_indexes
Revises: 0008_add_memory_v2
Create Date: 2026-08-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0009_align_query_indexes"
down_revision = "0008_add_memory_v2"
branch_labels = None
depends_on = None


INDEXES = (
    ("ix_daily_results_day", "daily_results", ["day"]),
    ("ix_daily_results_guild_id", "daily_results", ["guild_id"]),
    (
        "ix_relationship_interactions_user_a_id",
        "relationship_interactions",
        ["user_a_id"],
    ),
    (
        "ix_relationship_interactions_user_b_id",
        "relationship_interactions",
        ["user_b_id"],
    ),
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_by_table = {
        table_name: {
            index["name"] for index in inspector.get_indexes(table_name)
        }
        for _, table_name, _ in INDEXES
    }
    for index_name, table_name, columns in INDEXES:
        if index_name not in existing_by_table[table_name]:
            op.create_index(index_name, table_name, columns)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for index_name, table_name, _ in reversed(INDEXES):
        existing = {index["name"] for index in inspector.get_indexes(table_name)}
        if index_name in existing:
            op.drop_index(index_name, table_name=table_name)
