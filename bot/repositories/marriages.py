"""Marriage persistence."""

from __future__ import annotations

from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.marriage import Marriage
from bot.models.relationship import normalize_pair
from bot.repositories.base import Repository


class MarriageRepository(Repository):
    """Repository for marriage records."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_active_for_user(self, user_id: int) -> Marriage | None:
        """Return the active marriage row involving this user, if any."""

        statement: Select[tuple[Marriage]] = select(Marriage).where(
            or_(Marriage.user_a_id == user_id, Marriage.user_b_id == user_id)
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def create(self, user_one_id: int, user_two_id: int) -> Marriage:
        """Create and persist a new marriage row."""

        user_a_id, user_b_id = normalize_pair(user_one_id, user_two_id)
        record = Marriage(user_a_id=user_a_id, user_b_id=user_b_id)
        self.session.add(record)
        await self.session.flush()
        return record

    async def delete(self, record: Marriage) -> None:
        """Remove a marriage row."""

        await self.session.delete(record)
        await self.session.flush()