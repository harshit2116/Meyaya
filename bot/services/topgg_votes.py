"""Store verified Top.gg votes and grant one durable reward per vote."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from bot.models.topgg_vote import TopggVote

VOTE_CREDITS = 20
VOTE_LIFETIME = timedelta(hours=12)


class InvalidVote(ValueError):
    """Invalid authenticated payload; never include provider data in the message."""


def event_time(value) -> datetime:
    if not isinstance(value, str) or len(value) > 64:
        raise InvalidVote("Invalid vote time")
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(UTC)
    except (ValueError, OverflowError):
        raise InvalidVote("Invalid vote time") from None


@dataclass(frozen=True)
class VerifiedVote:
    vote_id: str
    user_id: int
    voted_at: datetime
    expires_at: datetime


class TopggVoteService:
    def __init__(self, session_factory):
        self.sessions = session_factory

    async def record(self, vote: VerifiedVote) -> bool:
        async with self.sessions() as session:
            inserted = await session.scalar(
                insert(TopggVote)
                .values(
                    vote_id=vote.vote_id,
                    user_id=vote.user_id,
                    voted_at=vote.voted_at,
                    expires_at=vote.expires_at,
                    credits=VOTE_CREDITS,
                    used=0,
                )
                .on_conflict_do_nothing()
                .returning(TopggVote.vote_id)
            )
            await session.commit()
        return inserted is not None

    async def status(self, user_id: int):
        now = datetime.now(UTC)
        async with self.sessions() as session:
            row = (
                await session.execute(
                    select(
                        TopggVote.voted_at, TopggVote.expires_at, TopggVote.credits, TopggVote.used
                    )
                    .where(TopggVote.user_id == user_id)
                    .order_by(TopggVote.voted_at.desc())
                    .limit(1)
                )
            ).first()
            remaining = await session.scalar(
                select(func.coalesce(func.sum(TopggVote.credits - TopggVote.used), 0)).where(
                    TopggVote.user_id == user_id,
                    TopggVote.expires_at > now,
                    TopggVote.voted_at <= now,
                )
            )
        return {"remaining": remaining, "expires_at": row.expires_at if row else None}

    @staticmethod
    async def reserve(session, user_id: int, now: datetime) -> str | None:
        # Lock the earliest expiring grant. Concurrent requests serialize on the
        # row, and the UPDATE condition is checked again after acquiring its lock.
        candidate = (
            select(TopggVote.vote_id)
            .where(
                TopggVote.user_id == user_id,
                TopggVote.expires_at > now,
                TopggVote.voted_at <= now,
                TopggVote.used < TopggVote.credits,
            )
            .order_by(TopggVote.expires_at, TopggVote.vote_id)
            .limit(1)
            .with_for_update()
            .scalar_subquery()
        )
        return await session.scalar(
            update(TopggVote)
            .where(
                TopggVote.vote_id == candidate,
                TopggVote.used < TopggVote.credits,
            )
            .values(used=TopggVote.used + 1)
            .returning(TopggVote.vote_id)
        )

    @staticmethod
    async def refund(session, vote_id: str) -> None:
        # An old in-flight generation must never refund a newer vote.
        await session.execute(
            update(TopggVote)
            .where(
                TopggVote.vote_id == vote_id,
                TopggVote.used > 0,
            )
            .values(used=TopggVote.used - 1)
        )
