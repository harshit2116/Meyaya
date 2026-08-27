"""Permanent bot memory persistence."""

from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.memory import BotMemory
from bot.repositories.base import Repository

MAX_MEMORIES_PER_GUILD = 200


class MemoryRepository(Repository):
    """Repository for permanent bot memories."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create(
        self,
        guild_id: int | None,
        content: str,
        *,
        channel_id: int | None = None,
        source_message_id: int | None = None,
        source_user_id: int | None = None,
        source_user_name: str | None = None,
        conversation_summary: str | None = None,
    ) -> BotMemory:
        """Store a new permanent memory."""

        record = BotMemory(
            guild_id=guild_id,
            channel_id=channel_id,
            source_message_id=source_message_id,
            source_user_id=source_user_id,
            source_user_name=source_user_name,
            content=content,
            conversation_summary=conversation_summary,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def list_recent(self, guild_id: int | None, limit: int = 25) -> list[BotMemory]:
        """Return the most recent memories for a guild, newest first."""

        statement: Select[tuple[BotMemory]] = (
            select(BotMemory)
            .where(BotMemory.guild_id == guild_id)
            .order_by(BotMemory.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())
