"""Atomic global identity creation; conflicts never update an existing character."""

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import delete, select, update

from bot.models.fantasy_profile import FantasyProfile
from bot.repositories.base import Repository


class FantasyProfileRepository(Repository):
    async def locked(self, user_id):
        result = await self.session.execute(
            select(FantasyProfile).where(FantasyProfile.user_id == user_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def replace_identity(self, user_id, values):
        result = await self.session.execute(
            update(FantasyProfile)
            .where(FantasyProfile.user_id == user_id)
            .values(**values)
            .returning(FantasyProfile)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one()

    async def reset(self, user_id):
        statement = (
            delete(FantasyProfile)
            .where(FantasyProfile.user_id == user_id)
            .returning(FantasyProfile.user_id)
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none() is not None

    async def get(self, user_id):
        return await self.session.get(FantasyProfile, user_id)

    async def create_if_absent(self, values):
        statement = (
            insert(FantasyProfile)
            .values(**values)
            .on_conflict_do_nothing(index_elements=[FantasyProfile.user_id])
            .returning(FantasyProfile)
        )
        result = await self.session.execute(statement)
        profile = result.scalar_one_or_none()
        if profile is not None:
            return profile, True
        # A separate READ COMMITTED statement sees the winning transaction
        # after ON CONFLICT has waited for it to commit. Never use DO UPDATE.
        profile = await self.get(values["user_id"])
        if profile is None:
            raise RuntimeError("The winning awakening could not be read")
        return profile, False
