"""User and statistics models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from bot.database.base import Base


class User(Base):
    """Discord user record."""

    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserStatistics(Base):
    """Aggregate interaction statistics for a user."""

    __tablename__ = "user_statistics"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    total_given: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hugs_given: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hugs_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    kisses_given: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    kisses_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pats_given: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pats_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_interactions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
