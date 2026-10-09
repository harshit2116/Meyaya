"""One restart-safe active campaign run per global soul."""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from bot.database.base import Base


class FantasyDungeonRun(Base):
    __tablename__ = "fantasy_dungeon_runs"
    __table_args__ = (
        CheckConstraint("floor BETWEEN 1 AND 10 AND encounter BETWEEN 0 AND 3", name="ck_dungeon_position"),
        CheckConstraint("hp >= 0 AND mp >= 0 AND revision >= 0", name="ck_dungeon_resources"),
        CheckConstraint("phase IN ('intro','combat','victory','story','boss_intro','cleared','seal','defeated','complete','abandoned')", name="ck_dungeon_phase"),
    )
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("fantasy_profiles.user_id", ondelete="CASCADE"), primary_key=True)
    token: Mapped[str] = mapped_column(String(32), nullable=False)
    floor: Mapped[int] = mapped_column(Integer, nullable=False)
    encounter: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    phase: Mapped[str] = mapped_column(String(20), nullable=False)
    hp: Mapped[int] = mapped_column(Integer, nullable=False)
    mp: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Bounded fighter snapshots, last reward and seal scene, never full transcripts.
    state: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


ACTIVE_PHASES = ("intro", "combat", "victory", "story", "boss_intro", "cleared", "seal")
