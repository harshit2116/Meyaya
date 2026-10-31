"""One global welcome marker per member; no message content is stored."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from bot.database.base import Base


class FirstUseGuide(Base):
    __tablename__ = "first_use_guides"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    shown_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    claim_token: Mapped[str | None] = mapped_column(String(32))
