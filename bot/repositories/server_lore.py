"""Persistence for shared server lore and inside jokes."""

from __future__ import annotations

import re

from sqlalchemy import Select, select

from bot.models.server_lore import ServerLore
from bot.repositories.base import Repository


class ServerLoreRepository(Repository):
    """Store recurring lore separately from personal permanent memories."""

    async def remember(
        self,
        guild_id: int,
        content: str,
        *,
        channel_id: int | None = None,
        message_id: int | None = None,
        user_id: int | None = None,
    ) -> ServerLore:
        """Create lore or reinforce an existing matching item."""

        clean_content = " ".join(content.split()).strip()[:1000]
        normalized_key = self._normalize(clean_content)
        statement: Select[tuple[ServerLore]] = select(ServerLore).where(
            ServerLore.guild_id == guild_id,
            ServerLore.normalized_key == normalized_key,
        )
        result = await self.session.execute(statement)
        record = result.scalar_one_or_none()
        if record is None:
            record = ServerLore(
                guild_id=guild_id,
                content=clean_content,
                normalized_key=normalized_key,
                source_channel_id=channel_id,
                source_message_id=message_id,
                source_user_id=user_id,
            )
            self.session.add(record)
        else:
            record.times_seen += 1
            record.content = clean_content
            record.source_channel_id = channel_id
            record.source_message_id = message_id
            record.source_user_id = user_id
        await self.session.flush()
        return record

    async def list_current(self, guild_id: int, limit: int = 20) -> list[ServerLore]:
        """Return the strongest recent lore for prompt context."""

        statement: Select[tuple[ServerLore]] = (
            select(ServerLore)
            .where(ServerLore.guild_id == guild_id)
            .order_by(ServerLore.times_seen.desc(), ServerLore.updated_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    @staticmethod
    def _normalize(content: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", " ", content.casefold()).strip()
        return normalized[:255] or "empty"
