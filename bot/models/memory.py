"""Permanent bot memory model."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from bot.database.base import Base


class MemoryStatus(StrEnum):
    """Lifecycle states for one structured personal fact."""

    ACTIVE = "active"
    CONFLICTED = "conflicted"
    SUPERSEDED = "superseded"


class BotMemory(Base):
    """A permanent fact Meyaya has chosen to remember about a server."""

    __tablename__ = "bot_memories"
    __table_args__ = (
        UniqueConstraint(
            "guild_id",
            "user_id",
            "category",
            "subject",
            "relation",
            name="uq_bot_memories_identity_relation",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    source_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    source_user_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str] = mapped_column(
        String(32), nullable=False, default="personal", server_default="personal"
    )
    subject: Mapped[str] = mapped_column(
        String(100), nullable=False, default="self", server_default="self"
    )
    relation: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.8, server_default="0.8"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=MemoryStatus.ACTIVE,
        server_default="active",
        index=True,
    )
    conflict_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    conflict_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    conflict_source_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    lifecycle_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    conversation_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
