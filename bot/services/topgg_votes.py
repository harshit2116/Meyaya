"""Store verified Top.gg votes and grant one durable reward per vote."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from bot.models.topgg_vote import TopggPollState, TopggVote

VOTE_CREDITS = 20
VOTE_LIFETIME = timedelta(hours=12)
POLL_LEASE = timedelta(seconds=45)
POLL_OVERLAP = timedelta(minutes=5)


class PollLeaseLost(RuntimeError):
    pass


@dataclass(frozen=True)
class PollCheckpoint:
    since: datetime
    started_at: datetime
    cursor: str | None


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
                    notify_attempted_at=None,
                )
                .on_conflict_do_nothing()
                .returning(TopggVote.vote_id)
            )
            await session.commit()
        return inserted is not None

    async def claim_notification(self, vote_id: str) -> bool:
        """Persist the one DM attempt before any external Discord operation."""
        now = datetime.now(UTC)
        async with self.sessions() as session:
            claimed = await session.scalar(
                update(TopggVote)
                .where(
                    TopggVote.vote_id == vote_id,
                    TopggVote.notify_attempted_at.is_(None),
                    TopggVote.expires_at > now,
                )
                .values(notify_attempted_at=now)
                .returning(TopggVote.vote_id)
            )
            await session.commit()
        return claimed is not None

    async def pending_notifications(self, *, limit=10):
        now = datetime.now(UTC)
        async with self.sessions() as session:
            rows = (
                await session.execute(
                    select(
                        TopggVote.vote_id,
                        TopggVote.user_id,
                        TopggVote.voted_at,
                        TopggVote.expires_at,
                    )
                    .where(
                        TopggVote.notify_attempted_at.is_(None),
                        TopggVote.expires_at > now,
                        TopggVote.voted_at <= now,
                    )
                    .order_by(TopggVote.voted_at, TopggVote.vote_id)
                    .limit(limit)
                )
            ).all()
        return [VerifiedVote(*row) for row in rows]

    async def acquire_poll(self, project_id: str, owner: str, *, now=None):
        now = now or datetime.now(UTC)
        async with self.sessions() as session:
            await session.execute(
                insert(TopggPollState).values(project_id=project_id).on_conflict_do_nothing()
            )
            state = await session.scalar(
                update(TopggPollState)
                .where(
                    TopggPollState.project_id == project_id,
                    or_(TopggPollState.lease_until.is_(None), TopggPollState.lease_until <= now),
                )
                .values(lease_owner=owner, lease_until=now + POLL_LEASE)
                .returning(TopggPollState)
            )
            if state is None:
                return None
            if state.scan_started_at is None:
                state.scan_started_at = now
                state.scan_since_at = (
                    max(state.completed_at - POLL_OVERLAP, now - VOTE_LIFETIME)
                    if state.completed_at
                    else now - VOTE_LIFETIME
                )
                state.cursor = None
            checkpoint = PollCheckpoint(state.scan_since_at, state.scan_started_at, state.cursor)
            await session.commit()
        return checkpoint

    async def store_poll_page(self, project_id: str, owner: str, page):
        now = datetime.now(UTC)
        async with self.sessions() as session:
            state = await session.scalar(
                select(TopggPollState)
                .where(
                    TopggPollState.project_id == project_id,
                    TopggPollState.lease_owner == owner,
                    TopggPollState.lease_until > now,
                )
                .with_for_update()
            )
            if state is None:
                raise PollLeaseLost("Vote poll lease expired")
            inserted = []
            if page.votes:
                rows = [
                    {
                        "vote_id": v.vote_id,
                        "user_id": v.user_id,
                        "voted_at": v.voted_at,
                        "expires_at": v.expires_at,
                        "credits": VOTE_CREDITS,
                        "used": 0,
                        "notify_attempted_at": None,
                    }
                    for v in page.votes
                ]
                inserted = (
                    await session.scalars(
                        insert(TopggVote)
                        .values(rows)
                        .on_conflict_do_nothing()
                        .returning(TopggVote.vote_id)
                    )
                ).all()
            if page.complete:
                state.completed_at = state.scan_started_at
                state.scan_started_at = state.scan_since_at = state.cursor = None
            else:
                state.cursor = page.cursor
            state.lease_until = now + POLL_LEASE
            await session.commit()
        return len(inserted)

    async def release_poll(self, project_id: str, owner: str):
        async with self.sessions() as session:
            await session.execute(
                update(TopggPollState)
                .where(
                    TopggPollState.project_id == project_id,
                    TopggPollState.lease_owner == owner,
                )
                .values(lease_owner=None, lease_until=None)
            )
            await session.commit()

    async def reset_poll_cursor(self, project_id: str, owner: str):
        now = datetime.now(UTC)
        async with self.sessions() as session:
            await session.execute(
                update(TopggPollState)
                .where(
                    TopggPollState.project_id == project_id,
                    TopggPollState.lease_owner == owner,
                )
                .values(scan_started_at=now, scan_since_at=now - VOTE_LIFETIME, cursor=None)
            )
            await session.commit()

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
