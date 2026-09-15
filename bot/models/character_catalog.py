"""Gameplay-only summon roster and durable safety controls."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from bot.database.base import Base


class CatalogCharacter(Base):
    """Meyaya-owned gameplay configuration; contains no AniList metadata."""

    __tablename__ = "summon_characters"
    __table_args__ = (UniqueConstraint("provider", "provider_character_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), default="anilist")
    provider_character_id: Mapped[str] = mapped_column(String(80))
    rarity_stars: Mapped[int] = mapped_column(Integer)
    summon_weight: Mapped[int] = mapped_column(Integer, default=100)
    class_name: Mapped[str] = mapped_column(String(80), default="Wanderer")
    traits: Mapped[list] = mapped_column(JSON, default=list)
    passive: Mapped[str] = mapped_column(String(250), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    image_disabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    takedown_reason: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CatalogProviderState(Base):
    __tablename__ = "catalog_provider_state"

    provider: Mapped[str] = mapped_column(String(40), primary_key=True)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    reason: Mapped[str] = mapped_column(Text, default="", server_default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CatalogAudit(Base):
    __tablename__ = "catalog_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[int] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(40))
    target: Mapped[str] = mapped_column(String(100))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
