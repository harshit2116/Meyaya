"""User data persistence."""

from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.user import User, UserStatistics
from bot.repositories.base import Repository


class UserRepository(Repository):
    """Repository for users and aggregate statistics."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def ensure_user(self, user_id: int) -> User:
        """Create the user record if it does not already exist."""

        statement: Select[tuple[User]] = select(User).where(User.user_id == user_id)
        result = await self.session.execute(statement)
        user = result.scalar_one_or_none()
        if user is not None:
            return user
        user = User(user_id=user_id)
        self.session.add(user)
        await self.session.flush()
        return user

    async def get_or_create_statistics(self, user_id: int) -> UserStatistics:
        """Fetch or initialize statistics for a user."""

        statement: Select[tuple[UserStatistics]] = select(UserStatistics).where(
            UserStatistics.user_id == user_id,
        )
        result = await self.session.execute(statement)
        stats = result.scalar_one_or_none()
        if stats is not None:
            return stats
        stats = UserStatistics(user_id=user_id)
        self.session.add(stats)
        await self.session.flush()
        return stats
