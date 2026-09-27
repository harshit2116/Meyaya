"""Best-effort typing indicators that never gate useful work."""

import asyncio
from contextlib import asynccontextmanager, suppress
import discord


@asynccontextmanager
async def background_typing(channel):
    async def indicate():
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
