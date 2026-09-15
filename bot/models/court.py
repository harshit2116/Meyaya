"""Persistent entertainment-only court cases."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from bot.database.base import Base


class CourtCase(Base):
    """One Meyaya court case with collected statements and final verdict."""

    __tablename__ = "court_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    plaintiff_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    defendant_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    charge: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    plaintiff_statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    defendant_statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    registered_witness_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    witness_statements: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    clarification_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    clarification_target: Mapped[str | None] = mapped_column(String(16), nullable=True)
    clarification_answers: Mapped[dict[str, str]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    verdict: Mapped[str | None] = mapped_column(String(32), nullable=True)
    plaintiff_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    defendant_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    decisive_factors: Mapped[str | None] = mapped_column(Text, nullable=True)
    punishment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CourtConfiguration(Base):
    """One overwriteable court channel selection per Discord server."""

    __tablename__ = "court_configurations"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_by_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
