"""Persistent mood and per-member relationship state for the Meyaya System."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from bot.database.base import Base


class MeyayaGlobalState(Base):
    """Meyaya's current emotional state within one Discord server."""

    __tablename__ = "meyaya_global_states"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    mood: Mapped[str] = mapped_column(
        String(24), nullable=False, default="normal", server_default="normal"
    )
    energy: Mapped[int] = mapped_column(
        Integer, nullable=False, default=70, server_default=text("70")
    )
    annoyance: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    mood_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mood_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    energy_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    annoyance_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class MeyayaUserState(Base):
    """Meyaya's evolving relationship with one member in one server."""

    __tablename__ = "meyaya_user_states"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    familiarity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    affection: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    annoyance: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    nickname: Mapped[str | None] = mapped_column(String(80), nullable=True)
    nickname_mode: Mapped[str] = mapped_column(
        String(12), nullable=False, default="auto", server_default="auto"
    )
    nickname_revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    nickname_mode: Mapped[str] = mapped_column(
        String(12), nullable=False, default="auto", server_default="auto"
    )
    nickname_revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_interaction_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    annoyance_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
