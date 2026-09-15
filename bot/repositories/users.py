"""User data persistence."""

from __future__ import annotations

from sqlalchemy import Select, select, update
from sqlalchemy.dialects.postgresql import insert
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

    async def record_interaction(
        self,
        actor_id: int,
        target_id: int,
        interaction_name: str,
    ) -> None:
        """Atomically create users/stat rows and increment both sides."""

        user_ids = sorted({actor_id, target_id})
        await self.session.execute(
            insert(User)
            .values([{"user_id": user_id} for user_id in user_ids])
            .on_conflict_do_nothing(index_elements=[User.user_id])
        )
        await self.session.execute(
            insert(UserStatistics)
            .values([{"user_id": user_id} for user_id in user_ids])
            .on_conflict_do_nothing(index_elements=[UserStatistics.user_id])
        )

        actor_values: dict[str, object] = {
            "total_given": UserStatistics.total_given + 1,
            "total_interactions": UserStatistics.total_interactions + 1,
        }
        target_values: dict[str, object] = {
            "total_received": UserStatistics.total_received + 1,
            "total_interactions": UserStatistics.total_interactions + 1,
        }
        given_field = {
            "hug": "hugs_given",
            "kiss": "kisses_given",
            "pat": "pats_given",
        }.get(interaction_name)
        received_field = {
            "hug": "hugs_received",
            "kiss": "kisses_received",
            "pat": "pats_received",
        }.get(interaction_name)
        if given_field is not None:
            actor_values[given_field] = getattr(UserStatistics, given_field) + 1
        if received_field is not None:
            target_values[received_field] = getattr(UserStatistics, received_field) + 1

        await self.session.execute(
            update(UserStatistics).where(UserStatistics.user_id == actor_id).values(**actor_values)
        )
        await self.session.execute(
            update(UserStatistics)
            .where(UserStatistics.user_id == target_id)
            .values(**target_values)
        )
