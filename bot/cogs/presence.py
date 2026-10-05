"""Fixed Soul Interface identity; no rotating task or API polling."""

import logging

import discord
from discord.ext import commands

logger = logging.getLogger(__name__)


STATUS_TEXT = "The Girl at the end of every story"
STATUS_EMOJI_ID = 1556562750409281637


def identity_activity() -> discord.CustomActivity:
    # Discord may omit custom-status emoji for bot presences.
    return discord.CustomActivity(
        name=STATUS_TEXT,
        emoji=discord.PartialEmoji(name="Meyaya", id=STATUS_EMOJI_ID),
    )


class PresenceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        # Reapply after reconnects; nothing periodically overwrites this identity.
        try:
            await self.bot.change_presence(
                status=discord.Status.dnd,
                activity=identity_activity(),
            )
        except (discord.HTTPException, ConnectionError, OSError):
            logger.warning("Identity presence unavailable; will retry after reconnect")


async def setup(bot):
    await bot.add_cog(PresenceCog(bot))
