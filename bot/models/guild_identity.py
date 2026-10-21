"""Last-known server identity, retained after the bot leaves."""
from sqlalchemy import BigInteger, String, Boolean, DateTime, Integer, func
from datetime import datetime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from bot.database.base import Base


class GuildIdentity(Base):
    __tablename__ = "guild_identities"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    owner_id: Mapped[int | None] = mapped_column(BigInteger)
    owner_name: Mapped[str | None] = mapped_column(String(100))
    icon_url: Mapped[str | None] = mapped_column(String(512))

    is_current: Mapped[bool | None] = mapped_column(Boolean)
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GuildEvent(Base):
    __tablename__ = 'guild_events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    event_type: Mapped[str] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor: Mapped[str | None] = mapped_column(String(80))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
