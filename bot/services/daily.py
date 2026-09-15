"""Daily fun command logic."""

from __future__ import annotations

from datetime import date
from hashlib import blake2b
from random import Random

from sqlalchemy.ext.asyncio import AsyncSession

from bot.repositories.daily import DailyRepository


class DailyService:
    """Resolve daily IQ and winner-style fun results."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.daily = DailyRepository(session)

    @staticmethod
    def iq_score(guild_id: int, user_id: int, day: date) -> int:
        """Return a stable daily IQ score for a guild member."""

        rng = Random(f"{guild_id}:{user_id}:{day.isoformat()}")
        return rng.randint(1, 200)

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
        # Python's built-in hash is randomized between processes. Persist a
        # stable compact value so restarts never alter stored metadata.
        record.iq_seed = (
            int.from_bytes(blake2b(seed.encode("utf-8"), digest_size=4).digest(), "big") % 1_000_000
        )
        await self.session.commit()
        return winner
