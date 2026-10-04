"""Global, permanent fantasy identity; guild progression may live separately."""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from bot.database.base import Base


class FantasyProfile(Base):
    __tablename__ = "fantasy_profiles"
    __table_args__ = (
        CheckConstraint("user_id > 0", name="ck_fantasy_user"),
        CheckConstraint("level >= 1 AND xp >= 0", name="ck_fantasy_progression"),
        CheckConstraint(
            "max_hp > 0 AND hp >= 0 AND hp <= max_hp AND max_mp > 0 AND mp >= 0 AND mp <= max_mp",
            name="ck_fantasy_resources",
        ),
        CheckConstraint(
            "strength > 0 AND dexterity > 0 AND intelligence > 0 AND vitality > 0 AND luck > 0",
            name="ck_fantasy_stats",
        ),
        CheckConstraint("generation_version >= 1", name="ck_fantasy_version"),
    )

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    generation_version: Mapped[int] = mapped_column(Integer, nullable=False)
    class_id: Mapped[str] = mapped_column(String(40), nullable=False)
    class_name: Mapped[str] = mapped_column(String(80), nullable=False)
    subclass_id: Mapped[str] = mapped_column(String(80), nullable=False)
    subclass_name: Mapped[str] = mapped_column(String(80), nullable=False)
    affinity_id: Mapped[str] = mapped_column(String(30), nullable=False)
    affinity_name: Mapped[str] = mapped_column(String(40), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    xp: Mapped[int] = mapped_column(BigInteger, nullable=False)
    hp: Mapped[int] = mapped_column(Integer, nullable=False)
    max_hp: Mapped[int] = mapped_column(Integer, nullable=False)
    mp: Mapped[int] = mapped_column(Integer, nullable=False)
    max_mp: Mapped[int] = mapped_column(Integer, nullable=False)
    strength: Mapped[int] = mapped_column(Integer, nullable=False)
    dexterity: Mapped[int] = mapped_column(Integer, nullable=False)
    intelligence: Mapped[int] = mapped_column(Integer, nullable=False)
    vitality: Mapped[int] = mapped_column(Integer, nullable=False)
    luck: Mapped[int] = mapped_column(Integer, nullable=False)
    base_stats: Mapped[dict] = mapped_column(JSON, nullable=False)
    weapon_id: Mapped[str] = mapped_column(String(120), nullable=False)
    weapon_name: Mapped[str] = mapped_column(String(100), nullable=False)
    weapon_family: Mapped[str] = mapped_column(String(30), nullable=False)
    weapon_type: Mapped[str] = mapped_column(String(50), nullable=False)
    weapon_rarity: Mapped[str] = mapped_column(String(30), nullable=False)
    weapon_lore: Mapped[str] = mapped_column(Text, nullable=False)
    weapon_trait: Mapped[str] = mapped_column(String(200), nullable=False)
    passive_id: Mapped[str] = mapped_column(String(80), nullable=False)
    passive_name: Mapped[str] = mapped_column(String(100), nullable=False)
    passive_description: Mapped[str] = mapped_column(Text, nullable=False)
    signature_id: Mapped[str] = mapped_column(String(80), nullable=False)
    signature_name: Mapped[str] = mapped_column(String(100), nullable=False)
    signature_description: Mapped[str] = mapped_column(Text, nullable=False)
    fantasy_title: Mapped[str] = mapped_column(String(150), nullable=False)
    alignment: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    meyaya_reaction: Mapped[str] = mapped_column(String(240), nullable=False)
    awakened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
