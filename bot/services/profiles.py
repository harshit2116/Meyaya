"""Optimized unified profile composition."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import and_, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.marriage import Marriage
from bot.models.meyaya_state import MeyayaGlobalState, MeyayaUserState
from bot.models.relationship import RelationshipInteraction
from bot.models.user import UserStatistics
from bot.services.marriage import MarriageService, MarriageSummary
from bot.services.meyaya_system import MeyayaProfileState, MeyayaSystemService


@dataclass(frozen=True, slots=True)
class ProfileSummary:
    """Display-ready profile information from two database round trips."""

    total_given: int
    total_received: int
    total_interactions: int
    favorite_interaction: str | None
    most_interacted_member_id: int | None
    meyaya: MeyayaProfileState
    marriage: MarriageSummary | None
    titles: tuple[str, ...]
    prompt_lines: tuple[str, ...] = ()


class ProfileService:
    """Build a unified profile without creating rows merely for viewing."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.meyaya_system = MeyayaSystemService(session)

    async def build(self, user_id: int, guild_id: int | None = None, *, display_name: str | None = None) -> ProfileSummary:
        """Load statistics, state, marriage, and social aggregates efficiently."""

        stats, global_state, user_state, marriage = await self._load_core(
            user_id,
            guild_id or 0,
        )
        favorite_interaction, most_interacted = await self._relationship_summary(user_id)
        meyaya = self.meyaya_system.profile_state_from_records(
            user_id,
            global_state,
            user_state,
        )
        marriage_summary = (
            MarriageService.summary_from_record(marriage, user_id) if marriage is not None else None
        )
        total_given = stats.total_given if stats is not None else 0
        total_received = stats.total_received if stats is not None else 0
        total_interactions = stats.total_interactions if stats is not None else 0
        return ProfileSummary(
            prompt_lines=tuple(self.meyaya_system.prompt_lines_from_records(
                user_id, display_name, global_state, user_state
            )) if display_name is not None else (),
            total_given=total_given,
            total_received=total_received,
            total_interactions=total_interactions,
            favorite_interaction=favorite_interaction,
            most_interacted_member_id=most_interacted,
            meyaya=meyaya,
            marriage=marriage_summary,
            titles=self._profile_titles(stats, meyaya),
        )

    async def _load_core(
        self,
        user_id: int,
        scope_id: int,
    ) -> tuple[
        UserStatistics | None,
        MeyayaGlobalState | None,
        MeyayaUserState | None,
        Marriage | None,
    ]:
        """Outer-join independent one-row records through a constant anchor."""

        anchor = select(literal(1).label("profile_anchor")).subquery()
        statement = (
            select(UserStatistics, MeyayaGlobalState, MeyayaUserState, Marriage)
            .select_from(anchor)
            .outerjoin(UserStatistics, UserStatistics.user_id == user_id)
            .outerjoin(MeyayaGlobalState, MeyayaGlobalState.guild_id == scope_id)
            .outerjoin(
                MeyayaUserState,
                and_(
                    MeyayaUserState.guild_id == scope_id,
                    MeyayaUserState.user_id == user_id,
                ),
            )
            .outerjoin(
                Marriage,
                or_(Marriage.user_a_id == user_id, Marriage.user_b_id == user_id),
            )
        )
        row = (await self.session.execute(statement)).first()
        if row is None:
            return None, None, None, None
        return row[0], row[1], row[2], row[3]

    async def _relationship_summary(self, user_id: int) -> tuple[str | None, int | None]:
        """Aggregate favorite action and closest member from one result set."""

        statement = select(
            RelationshipInteraction.user_a_id,
            RelationshipInteraction.user_b_id,
            RelationshipInteraction.interaction_type,
            RelationshipInteraction.interaction_count,
        ).where(
            (RelationshipInteraction.user_a_id == user_id)
            | (RelationshipInteraction.user_b_id == user_id)
        )
        rows = (await self.session.execute(statement)).all()
        return self._aggregate_relationship_rows(user_id, rows)

    @staticmethod
    def _aggregate_relationship_rows(
        user_id: int,
        rows: list[tuple[int, int, str, int]],
    ) -> tuple[str | None, int | None]:
        """Aggregate relationship rows with deterministic tie-breaking."""

        interaction_totals: dict[str, int] = {}
        member_totals: dict[int, int] = {}
        for left_id, right_id, interaction_type, count in rows:
            interaction_totals[interaction_type] = (
                interaction_totals.get(interaction_type, 0) + count
            )
            partner_id = right_id if left_id == user_id else left_id
            member_totals[partner_id] = member_totals.get(partner_id, 0) + count

        favorite = (
            min(
                interaction_totals,
                key=lambda interaction: (-interaction_totals[interaction], interaction),
            )
            if interaction_totals
            else None
        )
        closest = (
            min(member_totals, key=lambda member_id: (-member_totals[member_id], member_id))
            if member_totals
            else None
        )
        return favorite, closest

    @staticmethod
    def _profile_titles(
        stats: UserStatistics | None,
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
        if stats is not None:
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
            return ("🌱 Familiar Face",) if meyaya.familiarity >= 20 else ("🌸 New Face",)
        return tuple(titles[:3])
