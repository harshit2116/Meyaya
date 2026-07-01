"""Profile composition logic."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.relationship import RelationshipInteraction
from bot.repositories.users import UserRepository


@dataclass(frozen=True, slots=True)
class ProfileSummary:
    """Display-ready profile information."""

    total_given: int
    total_received: int
    favorite_interaction: str | None
    most_interacted_member_id: int | None


class ProfileService:
    """Build a profile summary from user and relationship data."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def build(self, user_id: int) -> ProfileSummary:
        """Compose the profile summary for a user."""

        stats = await self.users.get_or_create_statistics(user_id)
        favorite_interaction = await self._favorite_interaction(user_id)
        most_interacted = await self._most_interacted_member(user_id)
        return ProfileSummary(
            total_given=stats.total_given,
            total_received=stats.total_received,
            favorite_interaction=favorite_interaction,
            most_interacted_member_id=most_interacted,
        )

    async def _favorite_interaction(self, user_id: int) -> str | None:
        statement: Select[tuple[str, int]] = select(
            RelationshipInteraction.interaction_type,
            func.sum(RelationshipInteraction.interaction_count),
        ).where(
            (RelationshipInteraction.user_a_id == user_id) | (RelationshipInteraction.user_b_id == user_id),
        ).group_by(RelationshipInteraction.interaction_type).order_by(func.sum(RelationshipInteraction.interaction_count).desc())
        result = await self.session.execute(statement)
        row = result.first()
        return row[0] if row else None

    async def _most_interacted_member(self, user_id: int) -> int | None:
        statement: Select[tuple[int, int]] = select(
            RelationshipInteraction.user_a_id,
            RelationshipInteraction.user_b_id,
        ).where(
            (RelationshipInteraction.user_a_id == user_id) | (RelationshipInteraction.user_b_id == user_id),
        ).order_by(RelationshipInteraction.interaction_count.desc())
        result = await self.session.execute(statement)
        row = result.first()
        if row is None:
            return None
        left_id, right_id = row
        return right_id if left_id == user_id else left_id
