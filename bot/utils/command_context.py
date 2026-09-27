"""Separate command work from Discord response delivery in slow-command logs."""

import logging
import time
from discord.ext import commands

logger = logging.getLogger(__name__)


class TimedContext(commands.Context):
    async def send(self, *args, **kwargs):
        started = time.monotonic()
        try:
            return await super().send(*args, **kwargs)
        finally:
            elapsed = (time.monotonic() - started) * 1000
            if elapsed >= 500:
                logger.info("discord_delivery command=%s send_ms=%.0f",
                            getattr(self.command, "qualified_name", "unknown"), elapsed)
