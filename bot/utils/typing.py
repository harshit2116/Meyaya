"""Best-effort typing indicators that never gate useful work."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any
import discord


@asynccontextmanager
async def background_typing(channel: Any) -> AsyncIterator[None]:
    async def indicate() -> None:
        try:
            async with channel.typing():
                await asyncio.Future()
        except (discord.HTTPException, OSError, TimeoutError):
            pass

    task = asyncio.create_task(indicate(), name="typing-indicator")
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
