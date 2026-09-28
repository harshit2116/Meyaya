"""Daily aggregate usage; no message content is retained."""

from datetime import date
from sqlalchemy import BigInteger, Date, Integer, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from bot.database.base import Base


class GuildUsage(Base):
    __tablename__ = "guild_usage"
    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    chats: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    commands: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    command_counts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict,
                                               server_default=text("'{}'::jsonb"))
