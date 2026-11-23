"""Atomic global identity creation; conflicts never update an existing character."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import delete, select, update

from bot.models.fantasy_profile import FantasyProfile
from bot.repositories.base import Repository


class FantasyProfileRepository(Repository):
    async def locked(self, user_id: int) -> FantasyProfile | None:
        result = await self.session.execute(
            select(FantasyProfile).where(FantasyProfile.user_id == user_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def replace_identity(
        self, user_id: int, values: Mapping[str, Any]
    ) -> FantasyProfile:
        result = await self.session.execute(
            update(FantasyProfile)
            .where(FantasyProfile.user_id == user_id)
            .values(**values)
            .returning(FantasyProfile)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one()

    async def reset(self, user_id: int) -> bool:
        statement = (
            delete(FantasyProfile)
            .where(FantasyProfile.user_id == user_id)
            .returning(FantasyProfile.user_id)
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none() is not None

    async def get(self, user_id: int) -> FantasyProfile | None:
        return await self.session.get(FantasyProfile, user_id)

    async def create_if_absent(
        self, values: Mapping[str, Any]
    ) -> tuple[FantasyProfile, bool]:
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
        profile = await self.get(int(values["user_id"]))
        if profile is None:
            raise RuntimeError("The winning awakening could not be read")
        return profile, False
