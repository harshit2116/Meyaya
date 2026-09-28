"""Separate command work from Discord response delivery in slow-command logs."""

import logging
import time
from bot.utils.command_timing import add_stage
from bot.utils.command_timing import add_stage
from discord.ext import commands

logger = logging.getLogger(__name__)


class TimedContext(commands.Context):
    async def defer(self, *, ephemeral=False):
        if self.interaction is not None and self.interaction.response.is_done():
            return
        return await super().defer(ephemeral=ephemeral)

    async def send(self, *args, **kwargs):
        loader = getattr(self, "_meyaya_loader", None)
        if loader is not None:
            await loader.stop()
        started = time.monotonic()
        try:
            return await super().send(*args, **kwargs)
        finally:
            elapsed = (time.monotonic() - started) * 1000
            add_stage('delivery_ms', elapsed)
            add_stage('delivery_ms', elapsed)
            if elapsed >= 500:
                logger.info("discord_delivery command=%s send_ms=%.0f",
                            getattr(self.command, "qualified_name", "unknown"), elapsed)
