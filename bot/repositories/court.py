"""Court case persistence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.court import CourtCase, CourtConfiguration
from bot.repositories.base import Repository


class CourtRepository(Repository):
    """Create and retrieve court cases."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create(
        self,
        *,
        guild_id: int,
        channel_id: int,
        plaintiff_id: int,
        defendant_id: int,
        charge: str,
    ) -> CourtCase:
        case = CourtCase(
            guild_id=guild_id,
            channel_id=channel_id,
            plaintiff_id=plaintiff_id,
            defendant_id=defendant_id,
            charge=charge,
            status="LOBBY",
            registered_witness_ids=[],
            witness_statements={},
            clarification_answers={},
        )
        self.session.add(case)
        await self.session.flush()
        return case

    async def get(self, case_id: int) -> CourtCase | None:
        result = await self.session.execute(
            select(CourtCase).where(CourtCase.id == case_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_configuration(
        self,
        guild_id: int,
        *,
        for_update: bool = False,
    ) -> CourtConfiguration | None:
        statement = select(CourtConfiguration).where(CourtConfiguration.guild_id == guild_id)
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def set_channel(
        self,
        guild_id: int,
        channel_id: int | None,
        updated_by_user_id: int,
    ) -> CourtConfiguration:
        """Create or overwrite one server's court configuration."""

        configuration = await self.get_configuration(guild_id, for_update=True)
        if configuration is None:
            configuration = CourtConfiguration(
                guild_id=guild_id,
                channel_id=channel_id,
                updated_by_user_id=updated_by_user_id,
            )
            self.session.add(configuration)
        else:
            configuration.channel_id = channel_id
            configuration.updated_by_user_id = updated_by_user_id
        await self.session.flush()
        return configuration
