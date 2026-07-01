"""Daily fun result models."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from bot.database.base import Base


class DailyResult(Base):
    """Stores per-guild daily results for fun commands."""

    __tablename__ = "daily_results"
    __table_args__ = (UniqueConstraint("guild_id", "day", name="uq_daily_result_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    dumbest_member_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    smartest_member_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    clown_member_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    iq_seed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
