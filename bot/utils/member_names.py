"""Resolve display identities without requiring a full server member cache."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Iterable
from time import monotonic
from typing import Any

import discord


class MemberNames:
    def __init__(self, bot: Any) -> None:
        self.bot = bot
        self._cache: OrderedDict[tuple[int | None, int, bool], tuple[float, Any]] = OrderedDict()
        self._slots = asyncio.Semaphore(3)

    async def resolve(
        self,
        guild: Any,
        user_id: int,
        *,
        known: Iterable[Any] = (),
        historical: bool = False,
    ) -> Any:
        for member in known:
            if member is not None and member.id == user_id:
                return member
        member = guild.get_member(user_id) if guild is not None else None
        if member is not None:
            return member
        key = (getattr(guild, "id", None), user_id, historical)
        cached = self._cache.get(key)
        if cached is not None and cached[0] > monotonic():
            self._cache.move_to_end(key)
            return cached[1]
        try:
            # Include queue time so large historical lists cannot stall a command.
            async with asyncio.timeout(3), self._slots:
                fetch = getattr(guild, "fetch_member", None)
                if fetch is not None:
                    try:
                        member = await fetch(user_id)
                    except discord.NotFound:
                        pass
                if member is None and historical:
                    getter = getattr(self.bot, "get_user", None)
                    member = getter(user_id) if getter is not None else None
                    fetch = getattr(self.bot, "fetch_user", None)
                    if member is None and fetch is not None:
                        member = await fetch(user_id)
        except (discord.HTTPException, discord.ClientException, TimeoutError):
            # Historical records remain usable when someone left or Discord fails.
            pass
        self._cache[key] = (monotonic() + (60 if member is not None else 10), member)
        self._cache.move_to_end(key)
        while len(self._cache) > 256:
            self._cache.popitem(last=False)
        return member
