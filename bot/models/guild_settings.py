"""Persistent per-server configuration."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from bot.database.base import Base


class GuildSettings(Base):
    """Configuration owned by one Discord server."""

    __tablename__ = "guild_settings"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    command_prefix: Mapped[str] = mapped_column(
        String(10), nullable=False, default="uwu", server_default="uwu"
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    chat_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    daily_chat_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="40", default=40
    )
    autoresponder_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
