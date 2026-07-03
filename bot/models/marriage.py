"""Marriage models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from bot.database.base import Base


class Marriage(Base):
    """An active marriage between two users."""

    __tablename__ = "marriages"
    __table_args__ = (
        UniqueConstraint("user_a_id", "user_b_id", name="uq_marriage_pair"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_a_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    user_b_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    married_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())