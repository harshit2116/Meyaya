"""Per-server configuration persistence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.guild_settings import GuildSettings
from bot.repositories.base import Repository


class GuildSettingsRepository(Repository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_prefixes(self) -> dict[int, str]:
        result = await self.session.execute(
            select(GuildSettings.guild_id, GuildSettings.command_prefix)
        )
        return {int(guild_id): str(prefix) for guild_id, prefix in result.all()}

    async def list_autoresponders(self) -> dict[int, bool]:
        result = await self.session.execute(
            select(GuildSettings.guild_id, GuildSettings.autoresponder_enabled)
        )
        return {int(guild_id): bool(enabled) for guild_id, enabled in result.all()}

    async def list_chat_channels(self) -> dict[int, int | None]:
        result = await self.session.execute(
            select(GuildSettings.guild_id, GuildSettings.chat_channel_id)
        )
        return dict(result.all())

    async def set_chat_channel(self, guild_id: int, channel_id: int | None, actor_id: int):
        values = {"chat_channel_id": channel_id, "updated_by_user_id": actor_id}
        await self.session.execute(
            insert(GuildSettings)
            .values(guild_id=guild_id, **values)
            .on_conflict_do_update(index_elements=[GuildSettings.guild_id], set_=values)
        )

    async def set_autoresponder(self, guild_id: int, enabled: bool, actor_id: int) -> None:
        await self.session.execute(
            insert(GuildSettings)
            .values(guild_id=guild_id, autoresponder_enabled=enabled, updated_by_user_id=actor_id)
            .on_conflict_do_update(
                index_elements=[GuildSettings.guild_id],
                set_={"autoresponder_enabled": enabled, "updated_by_user_id": actor_id},
            )
        )

    async def set_prefix(
        self,
        guild_id: int,
        prefix: str,
        updated_by_user_id: int,
    ) -> str:
        statement = (
            insert(GuildSettings)
            .values(
                guild_id=guild_id,
                command_prefix=prefix,
                updated_by_user_id=updated_by_user_id,
            )
            .on_conflict_do_update(
                index_elements=[GuildSettings.guild_id],
                set_={
                    "command_prefix": prefix,
                    "updated_by_user_id": updated_by_user_id,
                },
            )
            .returning(GuildSettings.command_prefix)
        )
        return str((await self.session.execute(statement)).scalar_one())
