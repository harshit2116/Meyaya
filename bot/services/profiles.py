"""Profile composition logic."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.relationship import RelationshipInteraction
from bot.models.user import UserStatistics
from bot.repositories.users import UserRepository
from bot.services.meyaya_system import MeyayaProfileState, MeyayaSystemService


@dataclass(frozen=True, slots=True)
class ProfileSummary:
    """Display-ready profile information."""

    total_given: int
    total_received: int
    favorite_interaction: str | None
    most_interacted_member_id: int | None
    meyaya: MeyayaProfileState
    titles: tuple[str, ...]


class ProfileService:
    """Build a profile summary from user and relationship data."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.meyaya_system = MeyayaSystemService(session)

    async def build(self, user_id: int, guild_id: int | None = None) -> ProfileSummary:
        """Compose the profile summary for a user."""

        stats = await self.users.get_or_create_statistics(user_id)
        favorite_interaction = await self._favorite_interaction(user_id)
        most_interacted = await self._most_interacted_member(user_id)
        meyaya = await self.meyaya_system.profile_state(guild_id, user_id)
        return ProfileSummary(
            total_given=stats.total_given,
            total_received=stats.total_received,
            favorite_interaction=favorite_interaction,
            most_interacted_member_id=most_interacted,
            meyaya=meyaya,
            titles=self._profile_titles(stats, meyaya),
        )

    @staticmethod
    def _profile_titles(
        stats: UserStatistics,
        meyaya: MeyayaProfileState,
    ) -> tuple[str, ...]:
        """Choose a small set of earned titles for a clean profile."""

        titles: list[str] = []
        if meyaya.is_parent:
            titles.append("👑 Meyaya's Parent")
        if meyaya.user_annoyance >= 60:
            titles.append("😈 Professional Menace")
        if meyaya.affection >= 60:
            titles.append("💗 Meyaya's Favorite")
        if meyaya.familiarity >= 80:
            titles.append("🌟 Inner Circle")
        if stats.hugs_given >= 25:
            titles.append("🫂 Certified Hugger")
        if stats.kisses_given >= 25:
            titles.append("💋 Hopeless Romantic")
        if stats.pats_given >= 25:
            titles.append("🤍 Headpat Expert")
        if stats.total_given >= 100:
            titles.append("🎉 Social Butterfly")
        if stats.total_received >= 100:
            titles.append("✨ Server Sweetheart")
        if stats.total_interactions >= 250:
            titles.append("🏆 Interaction Legend")

        if not titles:
            if meyaya.familiarity >= 20:
                return ("🌱 Familiar Face",)
            return ("🌸 New Face",)
        return tuple(titles[:3])

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
