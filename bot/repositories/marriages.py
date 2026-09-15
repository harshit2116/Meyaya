"""Marriage persistence."""

from __future__ import annotations

from sqlalchemy import Select, and_, or_, select
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

    async def get_active_for_users(self, user_ids: set[int]) -> list[Marriage]:
        """Load every marriage involving any requested member in one query."""

        if not user_ids:
            return []
        statement: Select[tuple[Marriage]] = select(Marriage).where(
            or_(Marriage.user_a_id.in_(user_ids), Marriage.user_b_id.in_(user_ids))
        )
        return list((await self.session.scalars(statement)).all())

    async def get_exact_for_divorce(
        self,
        marriage_id: int,
        user_id: int,
        partner_id: int,
    ) -> Marriage | None:
        """Lock the exact marriage shown by a divorce confirmation."""

        user_a_id, user_b_id = normalize_pair(user_id, partner_id)
        statement: Select[tuple[Marriage]] = (
            select(Marriage)
            .where(
                and_(
                    Marriage.id == marriage_id,
                    Marriage.user_a_id == user_a_id,
                    Marriage.user_b_id == user_b_id,
                )
            )
            .with_for_update()
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
