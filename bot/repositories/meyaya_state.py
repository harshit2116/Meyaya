"""Persistence helpers for the Meyaya System."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.meyaya_state import MeyayaGlobalState, MeyayaUserState
from bot.repositories.base import Repository


class MeyayaStateRepository(Repository):
    """Load and create global and per-user personality state."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_global(self, guild_id: int, *, for_update: bool = False) -> MeyayaGlobalState | None:
        statement = select(MeyayaGlobalState).where(MeyayaGlobalState.guild_id == guild_id)
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_user(
        self, guild_id: int, user_id: int, *, for_update: bool = False
    ) -> MeyayaUserState | None:
        statement = select(MeyayaUserState).where(
            MeyayaUserState.guild_id == guild_id,
            MeyayaUserState.user_id == user_id,
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_users(
        self, guild_id: int, user_ids: list[int]
    ) -> dict[int, MeyayaUserState]:
        """Load multiple member states in one query, keyed by Discord user ID."""

        if not user_ids:
            return {}
        statement = select(MeyayaUserState).where(
            MeyayaUserState.guild_id == guild_id,
            MeyayaUserState.user_id.in_(user_ids),
        )
        result = await self.session.execute(statement)
        return {state.user_id: state for state in result.scalars()}

    async def get_or_create_global(self, guild_id: int) -> MeyayaGlobalState:
        state = await self.get_global(guild_id, for_update=True)
        if state is None:
            state = MeyayaGlobalState(guild_id=guild_id)
            self.session.add(state)
            await self.session.flush()
        return state

    async def get_or_create_user(self, guild_id: int, user_id: int) -> MeyayaUserState:
        state = await self.get_user(guild_id, user_id, for_update=True)
        if state is None:
            state = MeyayaUserState(guild_id=guild_id, user_id=user_id)
            self.session.add(state)
            await self.session.flush()
        return state
