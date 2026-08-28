"""Permanent bot memory persistence."""

from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.memory import BotMemory
from bot.repositories.base import Repository


class MemoryRepository(Repository):
    """Repository for permanent bot memories."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def remember(
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
        """Store one member fact, reusing an identical existing memory."""

        clean_content = " ".join(content.split()).strip()[:1000]
        statement: Select[tuple[BotMemory]] = select(BotMemory).where(
            BotMemory.guild_id == guild_id,
            BotMemory.source_user_id == source_user_id,
            func.lower(BotMemory.content) == clean_content.casefold(),
        )
        result = await self.session.execute(statement)
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.channel_id = channel_id
            existing.source_message_id = source_message_id
            existing.source_user_name = source_user_name
            existing.conversation_summary = conversation_summary
            await self.session.flush()
            return existing

        record = BotMemory(
            guild_id=guild_id,
            channel_id=channel_id,
            source_message_id=source_message_id,
            source_user_id=source_user_id,
            source_user_name=source_user_name,
            content=clean_content,
            conversation_summary=conversation_summary,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def list_for_user(
        self,
        guild_id: int | None,
        user_id: int,
        limit: int = 25,
    ) -> list[BotMemory]:
        """Return memories belonging to one canonical Discord identity."""

        statement: Select[tuple[BotMemory]] = (
            select(BotMemory)
            .where(
                BotMemory.guild_id == guild_id,
                BotMemory.source_user_id == user_id,
            )
            .order_by(BotMemory.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())
