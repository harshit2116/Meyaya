"""Daily fun command logic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from random import Random

from sqlalchemy.ext.asyncio import AsyncSession

from bot.repositories.daily import DailyRepository
from bot.repositories.users import UserRepository


@dataclass(frozen=True, slots=True)
class DailySelection:
    """A guild-scoped daily winner or score."""

    value: int | None = None
    member_id: int | None = None


class DailyService:
    """Resolve daily IQ and winner-style fun results."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.daily = DailyRepository(session)
        self.users = UserRepository(session)

    async def iq_score(self, guild_id: int, user_id: int, day: date) -> int:
        """Return a stable daily IQ score for a guild member."""

        await self.users.ensure_user(user_id)
        rng = Random(f"{guild_id}:{user_id}:{day.isoformat()}")
        score = rng.randint(1, 200)
        await self.session.commit()
        return score

    async def daily_winner(self, guild_id: int, day: date, kind: str, candidates: list[int]) -> int:
        """Return a stable daily winner from the provided candidate IDs."""

        record = await self.daily.get_or_create(guild_id, day)
        existing = {
            "dumbest": record.dumbest_member_id,
            "smartest": record.smartest_member_id,
            "clown": record.clown_member_id,
        }[kind]
        if existing is not None:
            return existing
        seed = f"{guild_id}:{day.isoformat()}:{kind}"
        rng = Random(seed)
        winner = rng.choice(candidates)
        if kind == "dumbest":
            record.dumbest_member_id = winner
        elif kind == "smartest":
            record.smartest_member_id = winner
        elif kind == "clown":
            record.clown_member_id = winner
        else:
            raise ValueError(f"Unknown daily winner kind: {kind}")
        record.iq_seed = abs(hash(seed)) % 1_000_000
        await self.session.commit()
        return winner
