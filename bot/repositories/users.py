"""User data persistence."""

from __future__ import annotations

from sqlalchemy import Select, select
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
        # One atomic upsert for both members. Merge self-interactions before
        # insertion: PostgreSQL cannot update the same conflict row twice.
        counters = ("total_given", "total_received", "total_interactions",
                    "hugs_given", "hugs_received", "kisses_given", "kisses_received",
                    "pats_given", "pats_received")
        increments = {uid: dict.fromkeys(counters, 0) for uid in user_ids}
        increments[actor_id]["total_given"] += 1
        increments[target_id]["total_received"] += 1
        increments[actor_id]["total_interactions"] += 1
        increments[target_id]["total_interactions"] += 1
        stem = {"hug": "hugs", "kiss": "kisses", "pat": "pats"}.get(interaction_name)
        if stem:
            increments[actor_id][stem + "_given"] += 1
            increments[target_id][stem + "_received"] += 1
        statement = insert(UserStatistics).values([
            dict(user_id=uid, **increments[uid]) for uid in user_ids
        ])
        result = await self.session.scalars(statement.on_conflict_do_update(
            index_elements=[UserStatistics.user_id],
            set_={field: getattr(UserStatistics, field) + getattr(statement.excluded, field)
                  for field in counters},
        ).returning(UserStatistics), execution_options={"populate_existing": True})
        # Keep any statistics already loaded in this session current as well.
        result.all()
