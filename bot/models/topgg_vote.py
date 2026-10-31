"""Verified Top.gg receipts and their expiring personal chat allowances."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from bot.database.base import Base


class TopggVote(Base):
    __tablename__ = "topgg_votes"
    __table_args__ = (
        UniqueConstraint("user_id", "voted_at", name="uq_topgg_user_vote_time"),
        CheckConstraint("used >= 0 AND used <= credits", name="ck_topgg_vote_credits"),
        CheckConstraint("credits = 20", name="ck_topgg_vote_reward"),
        Index("ix_topgg_votes_user_expiry", "user_id", "expires_at"),
        Index(
            "ix_topgg_votes_pending_dm",
            "voted_at",
            postgresql_where=text("notify_attempted_at IS NULL"),
        ),
    )

    vote_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    voted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False, server_default="20", default=20)
    used: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
    # Legacy writers may still run briefly while the schema is upgraded. Their
    # existing immediate DM flow stays attempted; new writers explicitly queue NULL.
    notify_attempted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TopggPollState(Base):
    """Resumable scan checkpoint and short lease for the one active poller."""

    __tablename__ = "topgg_poll_state"
    project_id: Mapped[str] = mapped_column(String(19), primary_key=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scan_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scan_since_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cursor: Mapped[str | None] = mapped_column(String(2048))
    lease_owner: Mapped[str | None] = mapped_column(String(32))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
