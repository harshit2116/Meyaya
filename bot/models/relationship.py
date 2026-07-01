"""Relationship interaction models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from bot.database.base import Base


def normalize_pair(user_one_id: int, user_two_id: int) -> tuple[int, int]:
    """Return a stable ordering for a relationship pair."""

    return tuple(sorted((user_one_id, user_two_id)))


class RelationshipInteraction(Base):
    """Shared interaction counter for a pair of users and an interaction type."""

    __tablename__ = "relationship_interactions"
    __table_args__ = (
        UniqueConstraint("user_a_id", "user_b_id", "interaction_type", name="uq_relationship_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_a_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    user_b_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    interaction_type: Mapped[str] = mapped_column(String(32), nullable=False)
    interaction_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_interaction_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
