"""Bot factory and lifecycle management."""

from __future__ import annotations

from contextlib import asynccontextmanager

import aiohttp
import discord
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from redis.asyncio import Redis

from bot.config.settings import Settings, get_settings
from bot.cache.redis import build_redis_client
from bot.database.session import build_async_engine, build_session_factory
from bot.logging.setup import configure_logging


class MeyayaBot(commands.Bot):
    """Discord bot configured for slash-command interaction."""

    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix=settings.command_prefix or "/", intents=intents)
        self.settings = settings
        self.engine = build_async_engine(settings.database_url)
        self.session_factory: async_sessionmaker[AsyncSession] = build_session_factory(self.engine)
        self.redis: Redis | None = None
        self.http_session: aiohttp.ClientSession | None = None

    @asynccontextmanager
    async def db_session(self) -> AsyncSession:
        """Provide a managed async database session to commands and services."""

        async with self.session_factory() as session:
            yield session

    async def setup_hook(self) -> None:
        """Load cogs and synchronize application commands."""

        self.redis = build_redis_client(self.settings.redis_url)
        self.http_session = aiohttp.ClientSession()
        await self.load_extension("bot.cogs.interactions")
        await self.load_extension("bot.cogs.daily")
        await self.load_extension("bot.cogs.profile")
        if self.settings.guild_id:
            guild = discord.Object(id=self.settings.guild_id)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def close(self) -> None:
        """Close external resources before shutting down the bot."""

        if self.http_session is not None and not self.http_session.closed:
            await self.http_session.close()
        if self.redis is not None:
            await self.redis.aclose()
        await self.engine.dispose()
        await super().close()

    async def on_ready(self) -> None:
        """Log the connected bot account."""

        print(f"Logged in as {self.user} ({self.user.id if self.user else 'unknown'})")


def create_bot() -> MeyayaBot:
    """Create a configured bot instance."""

    configure_logging()
    return MeyayaBot(get_settings())
