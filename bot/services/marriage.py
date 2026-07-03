"""Marriage business logic."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.marriage import Marriage
from bot.repositories.marriages import MarriageRepository


class AlreadyMarriedError(Exception):
    """Raised when a user involved in a proposal is already married."""

    def __init__(self, user_id: int) -> None:
        self.user_id = user_id
        super().__init__(f"User {user_id} is already married.")


class NotMarriedError(Exception):
    """Raised when a user tries to divorce without an active marriage."""


@dataclass(frozen=True)
class MarriageResult:
    user_a_id: int
    user_b_id: int


class MarriageService:
    """Handles marriage and divorce logic."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.marriages = MarriageRepository(session)

    async def get_active_marriage(self, user_id: int) -> Marriage | None:
        """Return the caller's active marriage row, if any."""

        return await self.marriages.get_active_for_user(user_id)

    async def marry(self, proposer_id: int, target_id: int) -> MarriageResult:
        """Create a marriage after acceptance. Raises AlreadyMarriedError if either is taken."""

        if proposer_id == target_id:
            raise ValueError("A user cannot marry themselves.")

        if await self.marriages.get_active_for_user(proposer_id) is not None:
            raise AlreadyMarriedError(proposer_id)

        if await self.marriages.get_active_for_user(target_id) is not None:
            raise AlreadyMarriedError(target_id)

        record = await self.marriages.create(proposer_id, target_id)
        await self.session.commit()
        return MarriageResult(user_a_id=record.user_a_id, user_b_id=record.user_b_id)

    async def divorce(self, user_id: int) -> MarriageResult:
        """Dissolve the caller's active marriage. Raises NotMarriedError if none exists."""

        record = await self.marriages.get_active_for_user(user_id)
        if record is None:
            raise NotMarriedError(f"User {user_id} is not married.")

        result = MarriageResult(user_a_id=record.user_a_id, user_b_id=record.user_b_id)
        await self.marriages.delete(record)
        await self.session.commit()
        return result