"""Durable voice session time, split into UTC days."""
from datetime import date
from sqlalchemy import String, BigInteger, Date, Float
from sqlalchemy.orm import Mapped, mapped_column
from bot.database.base import Base


class GuildVoiceUsage(Base):
    __tablename__ = 'guild_voice_usage'
    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    seconds: Mapped[float] = mapped_column(Float, nullable=False)
