"""Memory System v2 lifecycle and conflict handling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.memory import BotMemory, MemoryStatus
from bot.repositories.memories import MemoryRepository
from bot.services.llm import MemoryAction, MemoryDirective


class MemoryOutcome(StrEnum):
    ADDED = "added"
    CONFIRMED = "confirmed"
    UPDATED = "updated"
    CONFLICTED = "conflicted"
    IGNORED = "ignored"
    FORGOTTEN = "forgotten"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class MemoryResult:
    outcome: MemoryOutcome
    memory: BotMemory | None


class MemoryService:
    """Apply validated memory instructions for one canonical Discord identity."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.memories = MemoryRepository(session)

    async def apply(
        self,
        directive: MemoryDirective,
        *,
        guild_id: int | None,
        user_id: int,
        channel_id: int | None = None,
        source_message_id: int | None = None,
        source_user_name: str | None = None,
        conversation_summary: str | None = None,
    ) -> MemoryResult:
        """Apply ADD, UPDATE, CONFLICT, IGNORE, or FORGET atomically."""

        if directive.action is MemoryAction.IGNORE:
            return MemoryResult(MemoryOutcome.IGNORED, None)
        if directive.action is MemoryAction.FORGET:
            deleted = await self.memories.forget_key(
                guild_id,
                user_id,
                directive.category,
                directive.relation,
            )
            return MemoryResult(
                MemoryOutcome.FORGOTTEN if deleted else MemoryOutcome.NOT_FOUND,
                None,
            )

        subject = "self"
        value = self._clean_value(directive.value)
        existing = await self.memories.get_for_update(
            guild_id,
            user_id,
            directive.category,
            subject,
            directive.relation,
        )
        if existing is None:
            record, created = await self.memories.create_or_get(
                guild_id=guild_id,
                user_id=user_id,
                category=directive.category,
                subject=subject,
                relation=directive.relation,
                value=value,
                confidence=directive.confidence,
                channel_id=channel_id,
                source_message_id=source_message_id,
                source_user_name=source_user_name,
                conversation_summary=conversation_summary,
            )
            if created:
                return MemoryResult(MemoryOutcome.ADDED, record)
            existing = record

        if self._same_value(existing.value, value):
            await self.memories.touch_confirmed(
                existing,
                confidence=directive.confidence,
                source_message_id=source_message_id,
            )
            return MemoryResult(MemoryOutcome.CONFIRMED, existing)

        if directive.action is MemoryAction.UPDATE:
            self._activate_value(
                existing,
                value=value,
                confidence=directive.confidence,
                source_message_id=source_message_id,
                channel_id=channel_id,
                source_user_name=source_user_name,
                conversation_summary=conversation_summary,
                reason="explicit_update",
            )
            await self.session.flush()
            return MemoryResult(MemoryOutcome.UPDATED, existing)

        existing.status = MemoryStatus.CONFLICTED
        existing.conflict_value = value
        existing.conflict_confidence = directive.confidence
        existing.conflict_source_message_id = source_message_id
        existing.lifecycle_reason = (
            "explicit_conflict"
            if directive.action is MemoryAction.CONFLICT
            else "contradictory_add"
        )
        existing.updated_at = datetime.now(UTC)
        await self.session.flush()
        return MemoryResult(MemoryOutcome.CONFLICTED, existing)

    async def resolve(
        self,
        *,
        guild_id: int | None,
        user_id: int,
        memory_id: int,
        use_new_value: bool,
    ) -> MemoryResult:
        """Resolve only a conflict owned by the requesting member."""

        record = await self.memories.get_owned_id_for_update(guild_id, user_id, memory_id)
        if record is None or record.status != MemoryStatus.CONFLICTED:
            return MemoryResult(MemoryOutcome.NOT_FOUND, record)

        if use_new_value and record.conflict_value:
            record.value = record.conflict_value
            record.confidence = record.conflict_confidence or record.confidence
            record.source_message_id = record.conflict_source_message_id or record.source_message_id
            outcome = MemoryOutcome.UPDATED
            reason = "conflict_accepted"
        else:
            outcome = MemoryOutcome.CONFIRMED
            reason = "conflict_rejected"
        record.status = MemoryStatus.ACTIVE
        record.conflict_value = None
        record.conflict_confidence = None
        record.conflict_source_message_id = None
        record.lifecycle_reason = reason
        record.last_confirmed_at = datetime.now(UTC)
        await self.session.flush()
        return MemoryResult(outcome, record)

    @staticmethod
    def _clean_value(value: str | None) -> str:
        clean = " ".join((value or "").split()).strip()[:1000]
        if not clean:
            raise ValueError("A memory value is required for this operation")
        return clean

    @staticmethod
    def _same_value(left: str, right: str) -> bool:
        return " ".join(left.casefold().split()) == " ".join(right.casefold().split())

    @staticmethod
    def _activate_value(
        record: BotMemory,
        *,
        value: str,
        confidence: float,
        source_message_id: int | None,
        channel_id: int | None,
        source_user_name: str | None,
        conversation_summary: str | None,
        reason: str,
    ) -> None:
        record.value = value
        record.confidence = confidence
        record.status = MemoryStatus.ACTIVE
        record.conflict_value = None
        record.conflict_confidence = None
        record.conflict_source_message_id = None
        record.source_message_id = source_message_id
        record.channel_id = channel_id
        record.source_user_name = source_user_name
        record.conversation_summary = conversation_summary
        record.lifecycle_reason = reason
        record.last_confirmed_at = datetime.now(UTC)
