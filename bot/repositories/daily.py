"""Persistence for daily fun results."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.daily import DailyResult
from bot.repositories.base import Repository


class DailyRepository(Repository):
    """Repository for server-scoped daily outcomes."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_or_create(self, guild_id: int, day: date) -> DailyResult:
        """Return the stored daily result row for a guild and day."""

        statement: Select[tuple[DailyResult]] = select(DailyResult).where(
            DailyResult.guild_id == guild_id,
            DailyResult.day == day,
        )
        result = await self.session.execute(statement)
        daily_result = result.scalar_one_or_none()
        if daily_result is not None:
            return daily_result
        daily_result = DailyResult(guild_id=guild_id, day=day)
        self.session.add(daily_result)
        await self.session.flush()
        return daily_result
