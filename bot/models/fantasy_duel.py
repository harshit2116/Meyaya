"""Compact durable results; battle resources never update fantasy_profiles."""

from datetime import datetime
from sqlalchemy import BigInteger, Integer, String, DateTime, JSON, CheckConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from bot.database.base import Base


class FantasyDuelResult(Base):
    __tablename__ = "fantasy_duel_results"
    __table_args__ = (
        CheckConstraint("challenger_id <> opponent_id", name="ck_duel_distinct"),
        CheckConstraint("rounds BETWEEN 1 AND 6", name="ck_duel_rounds"),
        CheckConstraint(
            "winner_id IS NULL OR winner_id IN (challenger_id, opponent_id)", name="ck_duel_winner"
        ),
        Index("ix_duel_challenger_time", "challenger_id", "created_at"),
        Index("ix_duel_opponent_time", "opponent_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    challenger_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    opponent_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    winner_id: Mapped[int | None] = mapped_column(BigInteger)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rules_version: Mapped[int] = mapped_column(Integer, nullable=False)
    rounds: Mapped[int] = mapped_column(Integer, nullable=False)
    arena: Mapped[str] = mapped_column(String(60), nullable=False)
    summary: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
