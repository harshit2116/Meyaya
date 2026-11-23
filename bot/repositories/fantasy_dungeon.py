"""Lock the canonical profile before the run in every mutating transaction."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import aliased

from bot.models.fantasy_dungeon import FantasyDungeonRun, ACTIVE_PHASES
from bot.models.fantasy_profile import FantasyProfile
from bot.database.session import dungeon_connection_reuse
from bot.repositories.base import Repository


class FantasyDungeonRepository(Repository):
    @staticmethod
    def soul_statement(user_id: int, *, lock: bool = False) -> Select[Any]:
        profile: Any = FantasyProfile
        run: Any = FantasyDungeonRun
        if lock:
            # Materialize the canonical profile lock before reading/locking the
            # run, matching every other fantasy mutation's lock order. The run
            # CTE depends on the locked profile; no FOR UPDATE on a nullable
            # outer-join side (which PostgreSQL rejects).
            profile_rows = (select(FantasyProfile)
                .where(FantasyProfile.user_id == user_id).with_for_update()
                .cte("dungeon_soul").prefix_with("MATERIALIZED", dialect="postgresql"))
            run_rows = (select(FantasyDungeonRun)
                .join(profile_rows, FantasyDungeonRun.user_id == profile_rows.c.user_id)
                .with_for_update(of=FantasyDungeonRun)
                .cte("dungeon_run").prefix_with("MATERIALIZED", dialect="postgresql"))
            profile, run = aliased(FantasyProfile, profile_rows), aliased(FantasyDungeonRun, run_rows)
        return (select(profile, run).outerjoin(run, run.user_id == profile.user_id)
                .where(profile.user_id == user_id))

    async def soul(
        self, user_id: int, *, lock: bool = False
    ) -> tuple[FantasyProfile | None, FantasyDungeonRun | None]:
        with dungeon_connection_reuse():
            result = await self.session.execute(self.soul_statement(user_id, lock=lock))
        row = result.one_or_none()
        return (row[0], row[1]) if row is not None else (None, None)

    async def get(self, user_id: int, *, lock: bool = False) -> FantasyDungeonRun | None:
        query = select(FantasyDungeonRun).where(FantasyDungeonRun.user_id == user_id)
        if lock:
            query = query.with_for_update()
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def active(self, user_id: int) -> bool:
        phase = (
            await self.session.execute(
                select(FantasyDungeonRun.phase).where(FantasyDungeonRun.user_id == user_id)
            )
        ).scalar_one_or_none()
        return phase in ACTIVE_PHASES

    async def any_active(self, user_ids: tuple[int, ...] | list[int]) -> bool:
        if not user_ids:
            return False
        hit = (
            await self.session.execute(
                select(FantasyDungeonRun.user_id)
                .where(
                    FantasyDungeonRun.user_id.in_(user_ids),
                    FantasyDungeonRun.phase.in_(ACTIVE_PHASES),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        return hit is not None
