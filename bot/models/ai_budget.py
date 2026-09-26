"""Durable daily safety budgets independent of member-facing chat allowances."""

from datetime import date
from sqlalchemy import BigInteger, Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from bot.database.base import Base


class AIBudget(Base):
    __tablename__ = "ai_budget"
    scope_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # 0 = global
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
