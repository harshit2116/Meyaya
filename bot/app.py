"""Bot factory and lifecycle management."""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.config.settings import Settings, get_settings
from bot.logging.setup import configure_logging


class MeyayaBot(commands.Bot):
    """Discord bot configured for slash-command interaction."""

    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix=settings.command_prefix or "/", intents=intents)
        self.settings = settings

    async def setup_hook(self) -> None:
        """Load cogs and synchronize application commands."""

        await self.load_extension("bot.cogs.interactions")
        await self.load_extension("bot.cogs.daily")
        await self.load_extension("bot.cogs.profile")
        if self.settings.guild_id:
            guild = discord.Object(id=self.settings.guild_id)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self) -> None:
        """Log the connected bot account."""

        print(f"Logged in as {self.user} ({self.user.id if self.user else 'unknown'})")


def create_bot() -> MeyayaBot:
    """Create a configured bot instance."""

    configure_logging()
    return MeyayaBot(get_settings())
