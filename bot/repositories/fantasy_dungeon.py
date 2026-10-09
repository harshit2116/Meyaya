"""Lock the canonical profile before the run in every mutating transaction."""

from sqlalchemy import select

from bot.models.fantasy_dungeon import FantasyDungeonRun, ACTIVE_PHASES
from bot.repositories.base import Repository


class FantasyDungeonRepository(Repository):
    async def get(self, user_id, *, lock=False):
        query = select(FantasyDungeonRun).where(FantasyDungeonRun.user_id == user_id)
        if lock:
            query = query.with_for_update()
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def active(self, user_id):
        run = await self.get(user_id)
        return run is not None and run.phase in ACTIVE_PHASES
