"""Durable one-time guide admission with a small cache for returning members."""

import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert

from bot.models.first_use import FirstUseGuide


@dataclass(frozen=True)
class GuideClaim:
    state: str
    token: str | None = None


class FirstUseService:
    def __init__(self, session_factory):
        self.sessions = session_factory
        self._seen = OrderedDict()

    def remember(self, user_id):
        self._seen[user_id] = time.monotonic() + 3600
        self._seen.move_to_end(user_id)
        while len(self._seen) > 2048:
            self._seen.popitem(last=False)

    async def claim(self, user_id):
        if self._seen.get(user_id, 0) > time.monotonic():
            self._seen.move_to_end(user_id)
            return GuideClaim("seen")
        now = datetime.now(UTC)
        token = uuid4().hex
        async with self.sessions() as session:
            inserted = await session.scalar(
                insert(FirstUseGuide)
                .values(
                    user_id=user_id,
                    shown_at=now,
                    claim_token=token,
                )
                .on_conflict_do_nothing()
                .returning(FirstUseGuide.user_id)
            )
            if inserted is not None:
                await session.commit()
                return GuideClaim("new", token)
            row = (
                await session.execute(
                    select(FirstUseGuide.shown_at, FirstUseGuide.claim_token).where(
                        FirstUseGuide.user_id == user_id
                    )
                )
            ).first()
        if row is None or (row.claim_token and row.shown_at > now - timedelta(seconds=15)):
            return GuideClaim("pending")
        self.remember(user_id)
        return GuideClaim("seen")

    async def finish(self, user_id, token):
        # Cache first: a slow optional DB acknowledgement must not repeat a guide
        # that Discord has already accepted. The durable admission survives a restart.
        self.remember(user_id)
        async with self.sessions() as session:
            await session.execute(
                update(FirstUseGuide)
                .where(
                    FirstUseGuide.user_id == user_id,
                    FirstUseGuide.claim_token == token,
                )
                .values(claim_token=None)
            )
            await session.commit()

    async def release(self, user_id, token):
        """Retry on a later message only when Discord definitely rejected delivery."""
        async with self.sessions() as session:
            await session.execute(
                delete(FirstUseGuide).where(
                    FirstUseGuide.user_id == user_id,
                    FirstUseGuide.claim_token == token,
                )
            )
            await session.commit()
        self._seen.pop(user_id, None)
