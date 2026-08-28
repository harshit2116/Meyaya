"""Shared server lore and inside jokes remembered by Meyaya."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from bot.database.base import Base


class ServerLore(Base):
    """A public recurring incident or inside joke shared by one server."""

    __tablename__ = "server_lore"
    __table_args__ = (
        UniqueConstraint("guild_id", "normalized_key", name="uq_server_lore_guild_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    times_seen: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
