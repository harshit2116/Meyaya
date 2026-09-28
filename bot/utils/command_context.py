"""Separate command work from Discord response delivery in slow-command logs."""

import logging
import time
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
            cleanup_started = time.monotonic()
            try:
                await loader.stop()
            finally:
                cleanup_ms = (time.monotonic() - cleanup_started) * 1000
                add_stage('loading_cleanup_ms', cleanup_ms)
                if cleanup_ms >= 500:
                    logger.info("discord_loading_cleanup command=%s cleanup_ms=%.0f",
                                getattr(self.command, "qualified_name", "unknown"), cleanup_ms)
        started = time.monotonic()
        try:
            return await super().send(*args, **kwargs)
        finally:
            elapsed = (time.monotonic() - started) * 1000
            add_stage('delivery_ms', elapsed)
            if elapsed >= 500:
                # API call duration includes library retries and pre/post-response
                # rate-limit waits; it is not message-visible latency.
                logger.info("discord_delivery command=%s api_call_ms=%.0f includes_rate_limit_waits=true",
                            getattr(self.command, "qualified_name", "unknown"), elapsed)
