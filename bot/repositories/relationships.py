"""Relationship interaction persistence."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert
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
        now = datetime.now(tz=timezone.utc)
        statement = (
            insert(RelationshipInteraction)
            .values(
                user_a_id=user_a_id,
                user_b_id=user_b_id,
                interaction_type=interaction_type,
                interaction_count=1,
                last_interaction_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_relationship_type",
                set_={
                    "interaction_count": RelationshipInteraction.interaction_count + 1,
                    "last_interaction_at": now,
                },
            )
            .returning(RelationshipInteraction.interaction_count)
        )
        return (await self.session.execute(statement)).scalar_one()
