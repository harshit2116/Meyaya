"""Bot factory and lifecycle management."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging

import aiohttp
import discord
from discord.ext import commands
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.cache.redis import build_redis_client
from bot.config.settings import Settings, get_settings
from bot.database.session import build_async_engine, build_session_factory
from bot.logging.setup import configure_logging
from bot.services.chat_memory import ChatMemoryService
from bot.services.gemini import GeminiService
from bot.services.interactions import InteractionService
from bot.services.klipy import KlipyService
from bot.services.marriage import MarriageService

logger = logging.getLogger(__name__)


def _build_prefix_resolver(configured_prefix: str):
    """Accept bot mentions plus case-insensitive written prefixes."""

    written_prefixes = {"uwu"}
    if configured_prefix.strip():
        written_prefixes.add(configured_prefix.strip())

    def resolve(bot: commands.Bot, message: discord.Message) -> list[str]:
        prefixes = list(commands.when_mentioned(bot, message))
        content = message.content or ""
        for candidate in written_prefixes:
            length = len(candidate)
            if (
                content[:length].casefold() == candidate.casefold()
                and len(content) > length
                and content[length].isspace()
            ):
                # Return the user's exact casing and one whitespace character so
                # discord.py can match it literally before parsing the command.
                prefixes.append(content[: length + 1])
        return prefixes

    return resolve


class MeyayaBot(commands.Bot):
    """Discord bot configured for slash-command interaction."""

    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(
            command_prefix=_build_prefix_resolver(settings.command_prefix),
            case_insensitive=True,
            intents=intents,
            help_command=None,
        )
        self.settings = settings
        self.engine = build_async_engine(settings.database_url)
        self.session_factory: async_sessionmaker[AsyncSession] = build_session_factory(self.engine)
        self.redis: Redis | None = None
        self.http_session: aiohttp.ClientSession | None = None
        self._klipy_service: KlipyService | None = None
        self._chat_memory_service: ChatMemoryService | None = None
        self._gemini_service: GeminiService | None = None

    @asynccontextmanager
    async def db_session(self) -> AsyncSession:
        """Provide a managed async database session to commands and services."""

        async with self.session_factory() as session:
            yield session

    async def setup_hook(self) -> None:
        """Load cogs and synchronize application commands."""

        self.redis = build_redis_client(self.settings.redis_url)
        self.http_session = aiohttp.ClientSession()
        # These services are stateless wrappers around shared clients. Reuse
        # them instead of allocating a new wrapper for every command/message.
        self._klipy_service = KlipyService(
            self.settings.klipy_api_key,
            self.settings.klipy_rating,
            self.http_session,
            self.redis,
        )
        self._chat_memory_service = ChatMemoryService(self.redis)
        self._gemini_service = GeminiService(
            self.settings.gemini_api_key,
            self.settings.gemini_model,
            self.http_session,
        )
        await self.load_extension("bot.cogs.interactions")
        await self.load_extension("bot.cogs.daily")
        await self.load_extension("bot.cogs.profile")
        await self.load_extension("bot.cogs.ship")
        await self.load_extension("bot.cogs.marriage")
        await self.load_extension("bot.cogs.chat")
        # Optional monitor cog (watches configured channels)
        await self.load_extension("bot.cogs.monitor")
        await self.load_extension("bot.cogs.voice_live")
        if self.settings.guild_id:
            guild = discord.Object(id=self.settings.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def close(self) -> None:
        """Close external resources before shutting down the bot."""

        voice_cog = self.get_cog("VoiceLiveCog")
        if voice_cog is not None:
            try:
                await voice_cog.cog_unload()
            except Exception:
                logger.exception("Failed to unload VoiceLiveCog cleanly")

        if self.http_session is not None and not self.http_session.closed:
            await self.http_session.close()
        if self.redis is not None:
            await self.redis.aclose()
        await self.engine.dispose()
        await super().close()

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        """Suppress noisy tracebacks for expected command errors."""

        if isinstance(error, commands.CommandNotFound):
            return
        logger.exception("Unhandled command error", exc_info=error)

    def build_klipy_service(self) -> KlipyService | None:
        """Return the shared Klipy service once runtime clients are ready."""

        return self._klipy_service

    def build_chat_memory_service(self) -> ChatMemoryService | None:
        """Return the shared short-term chat memory service."""

        return self._chat_memory_service

    def build_gemini_service(self) -> GeminiService | None:
        """Return the shared Gemini service once the HTTP client is ready."""

        return self._gemini_service

    def build_interaction_service(self, session: AsyncSession) -> InteractionService:
        """Create an interaction service bound to the current runtime resources."""

        return InteractionService(
            session,
            self.build_klipy_service(),
            meyaya_user_id=self.user.id if self.user is not None else None,
        )

    def build_marriage_service(self, session: AsyncSession) -> MarriageService:
        """Create a marriage service bound to the current database session."""

        return MarriageService(session)

    async def on_ready(self) -> None:
        """Log the connected bot account."""

        print(f"Logged in as {self.user} ({self.user.id if self.user else 'unknown'})")


def create_bot() -> MeyayaBot:
    """Create a configured bot instance."""

    configure_logging()
    return MeyayaBot(get_settings())
