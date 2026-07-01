"""Relationship interaction persistence."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.relationship import RelationshipInteraction, normalize_pair
from bot.repositories.base import Repository


class RelationshipRepository(Repository):
    """Repository for shared relationship counters."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def increment(self, user_one_id: int, user_two_id: int, interaction_type: str) -> int:
        """Increment and return the shared counter for a pair and interaction type."""

        user_a_id, user_b_id = normalize_pair(user_one_id, user_two_id)
        statement: Select[tuple[RelationshipInteraction]] = select(RelationshipInteraction).where(
            RelationshipInteraction.user_a_id == user_a_id,
            RelationshipInteraction.user_b_id == user_b_id,
            RelationshipInteraction.interaction_type == interaction_type,
        )
        result = await self.session.execute(statement)
        record = result.scalar_one_or_none()
        if record is None:
            record = RelationshipInteraction(
                user_a_id=user_a_id,
                user_b_id=user_b_id,
                interaction_type=interaction_type,
                interaction_count=0,
                last_interaction_at=datetime.now(tz=timezone.utc),
            )
            self.session.add(record)
        record.interaction_count += 1
        record.last_interaction_at = datetime.now(tz=timezone.utc)
        await self.session.flush()
        return record.interaction_count
