"""Structured permanent-memory persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import blake2b

from sqlalchemy import Select, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.memory import BotMemory, MemoryStatus
from bot.repositories.base import Repository


class MemoryRepository(Repository):
    """Store one current fact per verified member, subject, and relation."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def _lock_identity(
        self,
        guild_id: int | None,
        user_id: int,
        category: str,
        subject: str,
        relation: str,
    ) -> None:
        """Serialize one memory identity, including nullable direct-message scopes."""

        identity = f"{guild_id!s}|{user_id}|{category}|{subject}|{relation}"
        lock_key = int.from_bytes(
            blake2b(identity.encode("utf-8"), digest_size=8).digest(),
            byteorder="big",
            signed=True,
        )
        await self.session.execute(select(func.pg_advisory_xact_lock(lock_key)))

    async def get_for_update(
        self,
        guild_id: int | None,
        user_id: int,
        category: str,
        subject: str,
        relation: str,
    ) -> BotMemory | None:
        await self._lock_identity(guild_id, user_id, category, subject, relation)
        statement: Select[tuple[BotMemory]] = (
            select(BotMemory)
            .where(
                BotMemory.guild_id == guild_id,
                BotMemory.user_id == user_id,
                BotMemory.category == category,
                BotMemory.subject == subject,
                BotMemory.relation == relation,
            )
            .order_by(BotMemory.updated_at.desc(), BotMemory.id.desc())
            .limit(1)
            .with_for_update()
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def create_or_get(
        self,
        *,
        guild_id: int | None,
        user_id: int,
        category: str,
        subject: str,
        relation: str,
        value: str,
        confidence: float,
        channel_id: int | None,
        source_message_id: int | None,
        source_user_name: str | None,
        conversation_summary: str | None,
    ) -> tuple[BotMemory, bool]:
        values = dict(
            guild_id=guild_id,
            channel_id=channel_id,
            source_message_id=source_message_id,
            user_id=user_id,
            source_user_name=source_user_name,
            category=category,
            subject=subject,
            relation=relation,
            value=value,
            confidence=confidence,
            status=MemoryStatus.ACTIVE,
            conversation_summary=conversation_summary,
            lifecycle_reason="added",
        )
        statement = (
            insert(BotMemory)
            .values(**values)
            .on_conflict_do_nothing(constraint="uq_bot_memories_identity_relation")
            .returning(BotMemory)
        )
        created = (await self.session.execute(statement)).scalar_one_or_none()
        if created is not None:
            return created, True
        existing = await self.get_for_update(
            guild_id,
            user_id,
            category,
            subject,
            relation,
        )
        if existing is None:
            raise RuntimeError("Memory upsert completed without a readable row")
        return existing, False

    async def forget_key(
        self,
        guild_id: int | None,
        user_id: int,
        category: str,
        relation: str,
        *,
        subject: str = "self",
    ) -> bool:
        """Hard-delete one fact because member privacy overrides audit history."""

        statement = delete(BotMemory).where(
            BotMemory.guild_id == guild_id,
            BotMemory.user_id == user_id,
            BotMemory.category == category,
            BotMemory.subject == subject,
            BotMemory.relation == relation,
        )
        result = await self.session.execute(statement)
        return bool(result.rowcount)

    async def forget_id(
        self,
        guild_id: int | None,
        user_id: int,
        memory_id: int,
    ) -> bool:
        statement = delete(BotMemory).where(
            BotMemory.id == memory_id,
            BotMemory.guild_id == guild_id,
            BotMemory.user_id == user_id,
        )
        result = await self.session.execute(statement)
        return bool(result.rowcount)

    async def forget_all(self, guild_id: int | None, user_id: int) -> int:
        statement = delete(BotMemory).where(
            BotMemory.guild_id == guild_id,
            BotMemory.user_id == user_id,
        )
        result = await self.session.execute(statement)
        return int(result.rowcount or 0)

    async def get_owned_id_for_update(
        self,
        guild_id: int | None,
        user_id: int,
        memory_id: int,
    ) -> BotMemory | None:
        statement = (
            select(BotMemory)
            .where(
                BotMemory.id == memory_id,
                BotMemory.guild_id == guild_id,
                BotMemory.user_id == user_id,
            )
            .with_for_update()
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_for_user(
        self,
        guild_id: int | None,
        user_id: int,
        limit: int = 50,
        *,
        include_conflicted: bool = False,
    ) -> list[BotMemory]:
        statuses = [MemoryStatus.ACTIVE]
        if include_conflicted:
            statuses.append(MemoryStatus.CONFLICTED)
        statement: Select[tuple[BotMemory]] = (
            select(BotMemory)
            .where(
                BotMemory.guild_id == guild_id,
                BotMemory.user_id == user_id,
                BotMemory.status.in_(statuses),
            )
            .order_by(BotMemory.updated_at.desc(), BotMemory.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def touch_confirmed(
        self,
        record: BotMemory,
        *,
        confidence: float,
        source_message_id: int | None,
    ) -> None:
        record.confidence = max(record.confidence, confidence)
        record.source_message_id = source_message_id or record.source_message_id
        record.last_confirmed_at = datetime.now(UTC)
        record.lifecycle_reason = "confirmed"
        await self.session.flush()
