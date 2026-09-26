"""Bot factory and lifecycle management."""

from __future__ import annotations

from contextlib import asynccontextmanager
import asyncio
from contextlib import suppress
import logging
import time

import aiohttp
import discord
from discord.ext import commands
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from bot.cache.redis import build_redis_client
from bot.config.settings import Settings, get_settings
from bot.database.session import build_async_engine, build_session_factory
from bot.logging.setup import configure_logging
from bot.services.chat_memory import ChatMemoryService
from bot.services.llm import LLMProvider
from bot.services.llm_factory import create_llm_provider
from bot.services.interactions import InteractionService
from bot.services.klipy import KlipyService
from bot.services.marriage import MarriageService
from bot.repositories.guild_settings import GuildSettingsRepository
from bot.utils.embeds import meyaya_embed
from bot.utils.image_work import ImageBusy
from bot.utils.command_parameters import normalize_member_parameters
from bot.services.usage import ChatLimitReached, UsageService, is_silence
from bot.services.request_log import RequestLogService, slash_content
from bot.services.profile_aesthetic import ProfileAestheticService
from bot.services.chat_blacklist import ChatBlacklistService
from bot.services.ai_guard import AIGuard

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10)
HTTP_CONNECTION_LIMIT = 20
HTTP_CONNECTIONS_PER_HOST = 5


DEFAULT_COMMAND_PREFIX = "uwu"


def resolve_command_prefix(bot: commands.Bot, message: discord.Message) -> list[str]:
    """Accept mentions plus the current server's case-insensitive prefix."""

    prefixes = list(commands.when_mentioned(bot, message))
    guild = message.guild
    guild_id = guild.id if guild is not None else None
    getter = getattr(bot, "prefix_for_guild", None)
    candidate = getter(guild_id) if getter is not None else DEFAULT_COMMAND_PREFIX
    content = message.content or ""
    length = len(candidate)
    if content[:length].casefold() != candidate.casefold() or len(content) <= length:
        return prefixes
    if content[length].isspace():
        # Return the user's exact casing and one whitespace character so
        # discord.py can match it literally before parsing the command.
        prefixes.append(content[: length + 1])
    elif not candidate[-1].isalnum():
        # Symbol prefixes retain the familiar compact form, such as !help.
        prefixes.append(content[:length])
    return prefixes


class MeyayaBot(commands.Bot):
    """Discord bot configured for slash-command interaction."""

    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(
            command_prefix=resolve_command_prefix,
            case_insensitive=True,
            intents=intents,
            help_command=None,
            max_messages=settings.discord_message_cache_size,
            chunk_guilds_at_startup=settings.discord_chunk_on_startup,
        )
        self.settings = settings
        self.started_at = time.monotonic()
        self._guild_prefixes: dict[int, str] = {}
        self._guild_autoresponders: dict[int, bool] = {}
        self._guild_chat_channels: dict[int, int | None] | None = None
        self.engine = build_async_engine(settings.database_url)
        self.session_factory: async_sessionmaker[AsyncSession] = build_session_factory(self.engine)
        self.usage = UsageService(self.session_factory, settings.quota_exempt_guild_id)
        self.request_log = RequestLogService(self.session_factory)
        self.chat_blacklist = ChatBlacklistService(self.session_factory)
        self.ai_guard = AIGuard(self.session_factory, settings)
        self._request_log_maintenance = None
        self.dashboard = None
        self.redis: Redis | None = None
        self.http_session: aiohttp.ClientSession | None = None
        self._klipy_service: KlipyService | None = None
        self._chat_memory_service: ChatMemoryService | None = None
        self._llm_provider: LLMProvider | None = None
        self._profile_aesthetic_service: ProfileAestheticService | None = None
        self.tree.on_error = self.on_app_command_error
        self.tree.interaction_check = self._blacklist_interaction_check

    async def _blacklist_interaction_check(self, interaction):
        if self.chat_blacklist.is_blocked(interaction.guild_id, interaction.user.id):
            await interaction.response.defer(ephemeral=True)
            await interaction.delete_original_response()
            return False
        return True

    @asynccontextmanager
    async def db_session(self) -> AsyncSession:
        """Provide a managed async database session to commands and services."""

        async with self.session_factory() as session:
            yield session

    async def setup_hook(self) -> None:
        """Load cogs and synchronize application commands."""

        await self.chat_blacklist.load()
        if self.settings.dashboard_enabled:
            from bot.web.dashboard import Dashboard

            self.dashboard = Dashboard(self)
            await self.dashboard.start()
        self.redis = build_redis_client(
            self.settings.redis_url, verify_tls=self.settings.redis_tls_verify
        )
        try:
            await self.redis.ping()
            logger.info("Redis connected")
        except RedisError:
            logger.warning(
                "Redis unavailable. Continuing without short-term cache for this process."
            )
            if self.settings.redis_required:
                raise RuntimeError(
                    "Redis is required for this deployment but is unavailable"
                ) from None
            await self.redis.aclose()
            self.redis = None
        connector = aiohttp.TCPConnector(
            limit=HTTP_CONNECTION_LIMIT,
            limit_per_host=HTTP_CONNECTIONS_PER_HOST,
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
        )
        self.http_session = aiohttp.ClientSession(
            connector=connector,
            timeout=HTTP_TIMEOUT,
        )
        # These services are stateless wrappers around shared clients. Reuse
        # them instead of allocating a new wrapper for every command/message.
        self._klipy_service = KlipyService(
            self.settings.klipy_api_key,
            self.settings.klipy_rating,
            self.http_session,
            self.redis,
        )
        self._chat_memory_service = ChatMemoryService(self.redis)
        self._llm_provider = create_llm_provider(self.settings, self.http_session, self.ai_guard)
        self._profile_aesthetic_service = ProfileAestheticService(self)
        await self._load_guild_prefixes()
        self._request_log_maintenance = asyncio.create_task(
            self.request_log.maintenance(), name="request-log-retention"
        )
        await self.load_extension("bot.cogs.interactions")
        await self.load_extension("bot.cogs.daily")
        await self.load_extension("bot.cogs.profile")
        await self.load_extension("bot.cogs.profile_studio")
        await self.load_extension("bot.cogs.ship")
        await self.load_extension("bot.cogs.fun")
        await self.load_extension("bot.cogs.member_fun")
        await self.load_extension("bot.cogs.celestial")
        await self.load_extension("bot.cogs.character_catalog")
        await self.load_extension("bot.cogs.solo_games")
        await self.load_extension("bot.cogs.social_games")
        await self.load_extension("bot.cogs.marriage")
        await self.load_extension("bot.cogs.court")
        await self.load_extension("bot.cogs.fact_check")
        await self.load_extension("bot.cogs.memory")
        await self.load_extension("bot.cogs.roleplay")
        await self.load_extension("bot.cogs.chat")
        # Optional monitor cog (watches configured channels)
        await self.load_extension("bot.cogs.monitor")
        await self.load_extension("bot.cogs.voice_live")
        await self.load_extension("bot.cogs.admin")
        await self.load_extension("bot.cogs.moderation")
        await self.load_extension("bot.cogs.presence")
        normalize_member_parameters(self)
        synced = await self.tree.sync()
        logger.info("Synced %s global slash commands", len(synced))
        if self.settings.guild_id:
            guild = discord.Object(id=self.settings.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)

    async def close(self) -> None:
        """Close external resources before shutting down the bot."""

        if self._request_log_maintenance is not None:
            self._request_log_maintenance.cancel()
            with suppress(asyncio.CancelledError):
                await self._request_log_maintenance
            self._request_log_maintenance = None
        if self.dashboard is not None:
            await self.dashboard.close()
            self.dashboard = None
        voice_cog = self.get_cog("VoiceLiveCog")
        moderation_cog = self.get_cog("ModerationCog")
        if moderation_cog is not None:
            await moderation_cog.cog_unload()
        if voice_cog is not None:
            try:
                await voice_cog.cog_unload()
            except Exception:
                logger.exception("Failed to unload VoiceLiveCog cleanly")

        try:
            await super().close()
        finally:
            try:
                if self.http_session is not None and not self.http_session.closed:
                    await self.http_session.close()
            finally:
                try:
                    if self.redis is not None:
                        await self.redis.aclose()
                finally:
                    await self.engine.dispose()

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        """Return friendly written-command errors and log only unexpected failures."""

        if isinstance(error, commands.CommandNotFound):
            return
        original = getattr(error, "original", error)
        if isinstance(original, ImageBusy):
            message = str(original)
        elif isinstance(original, commands.CommandOnCooldown):
            message = f"That command needs a tiny break. Try again in {original.retry_after:.1f}s."
        elif isinstance(original, commands.MissingPermissions):
            message = "You do not have the server permissions needed for that command."
        elif isinstance(original, commands.BotMissingPermissions):
            message = "I am missing a Discord permission needed to do that here."
        elif isinstance(original, commands.MissingRequiredArgument):
            command_name = ctx.command.qualified_name if ctx.command is not None else "that"
            message = f"I am missing `{original.param.name}`. Try `/help command:{command_name}`."
        elif isinstance(original, (commands.BadArgument, commands.UserInputError)):
            message = "I could not understand one of those arguments. Check `/help` for the format."
        elif isinstance(original, commands.CheckFailure):
            message = "You cannot use that command here."
        else:
            logger.error(
                "Unhandled command error command=%s",
                ctx.command,
                exc_info=(type(original), original, original.__traceback__),
            )
            message = "Something unexpected interrupted that command. Nothing was changed."
        await ctx.send(
            embed=meyaya_embed("Tiny Hiccup", message, tone="danger", icon="💭"),
            ephemeral=ctx.interaction is not None,
        )

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError,
    ) -> None:
        """Return the same friendly error language for slash commands."""

        original = getattr(error, "original", error)
        if isinstance(original, ImageBusy):
            message = str(original)
        elif isinstance(original, discord.app_commands.CommandOnCooldown):
            message = f"That command needs a tiny break. Try again in {original.retry_after:.1f}s."
        elif isinstance(original, discord.app_commands.MissingPermissions):
            message = "You do not have the server permissions needed for that command."
        elif isinstance(original, discord.app_commands.BotMissingPermissions):
            message = "I am missing a Discord permission needed to do that here."
        elif isinstance(
            original,
            (discord.app_commands.TransformerError, discord.app_commands.CommandSignatureMismatch),
        ):
            message = "I could not understand those options. Open `/help` and try once more."
        elif isinstance(original, discord.app_commands.CheckFailure):
            message = "You cannot use that command here."
        else:
            logger.error(
                "Unhandled slash-command error command=%s",
                interaction.command,
                exc_info=(type(original), original, original.__traceback__),
            )
            message = "Something unexpected interrupted that command. Nothing was changed."
        payload = {
            "embed": meyaya_embed("Tiny Hiccup", message, tone="danger", icon="💭"),
            "ephemeral": True,
        }
        if interaction.response.is_done():
            await interaction.followup.send(**payload)
        else:
            await interaction.response.send_message(**payload)

    def build_klipy_service(self) -> KlipyService | None:
        """Return the shared Klipy service once runtime clients are ready."""

        return self._klipy_service

    def build_chat_memory_service(self) -> ChatMemoryService | None:
        """Return the shared short-term chat memory service."""

        return self._chat_memory_service

    def build_llm_provider(self) -> LLMProvider | None:
        """Return the configured LLM provider once the HTTP client is ready."""

        return self._llm_provider

    def build_profile_aesthetic_service(self) -> ProfileAestheticService:
        """Return the shared public-profile analyzer and its short-lived asset cache."""

        if self._profile_aesthetic_service is None:
            self._profile_aesthetic_service = ProfileAestheticService(self)
        return self._profile_aesthetic_service

    async def generate_chat(self, guild_id, *args, **kwargs):
        """Reserve before generation and refund failures or silence responses."""
        if guild_id is None:
            raise ChatLimitReached("Meyaya chat commands are only available inside a server.")
        day = await self.usage.reserve(guild_id) if guild_id is not None else None
        charged = False
        try:
            result = await self._llm_provider.generate(*args, **kwargs)
            charged = (
                result is not None and bool(result.text.strip()) and not is_silence(result.text)
            )
            return result
        finally:
            if day is not None and not charged:
                await self.usage.refund(guild_id, day)

    async def on_command_completion(self, ctx):
        # Hybrid commands also emit app-command completion; count them only there.
        if ctx.guild is not None and ctx.interaction is None:
            await self._count_command(ctx.guild.id)

    async def on_command(self, ctx):
        if ctx.interaction is None:
            await self.request_log.record_message(ctx.message, kind="command")

    async def on_message(self, message):
        if self.chat_blacklist.is_blocked(
            message.guild.id if message.guild else None, message.author.id
        ):
            return
        moderation = self.get_cog("ModerationCog")
        if moderation and await moderation.should_block(message):
            return
        await self.process_commands(message)

    async def on_interaction(self, interaction):
        if (
            interaction.type is not discord.InteractionType.application_command
            or interaction.guild_id is None
        ):
            return
        data = interaction.data or {}
        # Exclude message/user context menus, buttons and modal payloads.
        if data.get("type", 1) != 1:
            return
        await self.request_log.record(
            event_id=interaction.id,
            guild_id=interaction.guild_id,
            channel_id=interaction.channel_id,
            user_id=interaction.user.id,
            user_name=str(interaction.user),
            kind="slash",
            content=slash_content(data),
        )

    async def on_app_command_completion(self, interaction, command):
        if interaction.guild_id is not None:
            await self._count_command(interaction.guild_id)

    async def _count_command(self, guild_id):
        try:
            await self.usage.command_completed(guild_id)
        except SQLAlchemyError:
            logger.warning("Could not record command usage")

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

    def prefix_for_guild(self, guild_id: int | None) -> str:
        """Return one server's cached prefix, using uwu for DMs and new servers."""

        if guild_id is None:
            return DEFAULT_COMMAND_PREFIX
        return self._guild_prefixes.get(guild_id, DEFAULT_COMMAND_PREFIX)

    def cache_guild_prefix(self, guild_id: int, prefix: str) -> None:
        """Update the synchronous command-router cache after a committed change."""

        self._guild_prefixes[guild_id] = prefix

    def autoresponder_enabled(self, guild_id: int) -> bool:
        return self._guild_autoresponders.get(guild_id, False)

    def chat_allowed(self, guild_id: int, channel_id: int) -> bool:
        # If configuration could not load, don't accidentally bypass restrictions.
        if self._guild_chat_channels is None:
            return False
        bound = self._guild_chat_channels.get(guild_id)
        return bound is None or bound == channel_id

    def cache_autoresponder(self, guild_id: int, enabled: bool) -> None:
        self._guild_autoresponders[guild_id] = enabled

    async def _load_guild_prefixes(self) -> None:
        """Warm the prefix cache without preventing startup during a DB outage."""

        try:
            async with self.db_session() as session:
                self._guild_chat_channels = await GuildSettingsRepository(
                    session
                ).list_chat_channels()
                self._guild_prefixes = await GuildSettingsRepository(session).list_prefixes()
                self._guild_autoresponders = await GuildSettingsRepository(
                    session
                ).list_autoresponders()
        except SQLAlchemyError:
            logger.exception("Could not load server prefixes; using uwu until restart")
            self._guild_prefixes = {}

    async def on_ready(self) -> None:
        """Log the connected bot account."""

        print(f"Logged in as {self.user} ({self.user.id if self.user else 'unknown'})")


def create_bot() -> MeyayaBot:
    """Create a configured bot instance."""

    configure_logging()
    return MeyayaBot(get_settings())
