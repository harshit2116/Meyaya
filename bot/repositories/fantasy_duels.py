"""One idempotent insert per completed duel; no per-turn writes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from bot.models.fantasy_duel import FantasyDuelResult
from bot.repositories.base import Repository


class FantasyDuelRepository(Repository):
    async def record(self, values: Mapping[str, Any]) -> None:
        await self.session.execute(
            insert(FantasyDuelResult)
            .values(**values)
            .on_conflict_do_nothing(index_elements=[FantasyDuelResult.id])
        )
