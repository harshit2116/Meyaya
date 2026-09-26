"""A small rotating presence, with no model calls or background polling."""

import logging

import discord
from discord.ext import commands, tasks

logger = logging.getLogger(__name__)


def activity_for(index: int, server_count: int) -> discord.BaseActivity:
    activities = (
        discord.Game(name="/help • a little chaos, a lot of heart 🌸"),
        discord.Activity(type=discord.ActivityType.listening, name="your stories 💬 • @Meyaya"),
        discord.Game(name="/fortune • what’s your next chapter? 🔮"),
        discord.Activity(type=discord.ActivityType.watching,
                         name=f"over {server_count} {'server' if server_count == 1 else 'servers'} 🌷"),
        discord.Game(name="/ship • definitely not matchmaking 💞"),
        discord.Game(name="/summon • your next favorite awaits ✨"),
    )
    return activities[index % len(activities)]


class PresenceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.index = 0

    @commands.Cog.listener()
    async def on_ready(self):
        # Discord can dispatch ready again after a reconnect.
        if not self.rotate.is_running():
            self.rotate.start()

    @tasks.loop(minutes=15)
    async def rotate(self):
        await self.bot.wait_until_ready()
        try:
            await self.bot.change_presence(
                status=discord.Status.online,
                activity=activity_for(self.index, len(self.bot.guilds)),
            )
        except (discord.HTTPException, ConnectionError, OSError):
            logger.warning("Presence update unavailable; will retry on the next rotation")
            return
        self.index = (self.index + 1) % 6

    def cog_unload(self):
        self.rotate.cancel()


async def setup(bot):
    await bot.add_cog(PresenceCog(bot))
