"""Persistent moderation switches and permission snapshots."""

from sqlalchemy import BigInteger, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column
from bot.database.base import Base


class ModerationSettings(Base):
    __tablename__ = "moderation_settings"
    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    probation: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    cross_spam: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    anti_invite: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    raid_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class ChannelLock(Base):
    __tablename__ = "channel_locks"
    channel_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    single: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    raid: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
