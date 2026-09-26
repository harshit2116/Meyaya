"""Monitor configured channels and enforce their English-only rule.

Behavior:
- Loads monitored channels from settings and Redis.
- Detects and verifies predominantly non-English text.
- Tracks three warnings and applies a ten-minute Discord timeout.
"""

from __future__ import annotations

from bot.logging.telemetry import discord_context, event

from bot.prompts.monitor import build_moderation_instruction

import asyncio
import logging
import random
import re
import time
from datetime import timedelta
from weakref import WeakValueDictionary

import discord
from discord import app_commands
from discord.ext import commands

from bot.app import MeyayaBot
from bot.config.settings import get_settings
from bot.utils.embeds import meyaya_embed

logger = logging.getLogger(__name__)

MONITOR_CHANNELS_KEY = "monitor:channels"
MONITOR_WARNING_KEY_PREFIX = "monitor:english-warnings"
MONITOR_COOLDOWN_SECONDS = 25
WARNING_LIMIT = 3
WARNING_WINDOW_SECONDS = 86_400
TIMEOUT_DURATION = timedelta(minutes=10)

_ROMANIZED_HINDI_HINT_RE = re.compile(
    r"\b(kya|kaise|kaisa|kaisi|haan|han|nahi|nahin|acha|accha|aur|haal|chaal|bhai|yaar|namaste|shukriya)\b",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
# Strong English/chat markers take precedence over statistical detection. Short
# slang such as "ur" and "pls" is routinely misclassified by langdetect.
_ENGLISH_CHAT_HINT_RE = re.compile(
    r"\b(the|an|and|but|this|that|these|those|i|i'm|im|you|your|u|ur|we|they|he|she|it|"
    r"is|are|was|were|have|has|do|does|don't|dont|can|could|would|should|please|pls|"
    r"lol|lmao|bro|bruh)\b",
    re.IGNORECASE,
)

ENGLISH_NUDGES = (
    "Meyaya's language radar went beep - English in this channel, please 😼",
    "Quick Meyaya checkpoint: let's keep this channel in English ✨",
    "English mode, pretty please? Meyaya wants everyone in the loop 💫",
    "Tiny language bonk: please use English in this channel 🔨",
    "Meyaya patrol reporting in: English chat only here 🫡",
    "Let's switch that to English so nobody gets left out 🌸",
    "English for the next message, deal? Meyaya is keeping count 😸",
    "A gentle reminder from Meyaya: please keep the chat in English 🌷",
)


class MonitorCog(commands.Cog):
    def __init__(self, bot: MeyayaBot) -> None:
        self.bot = bot
        self.settings = get_settings()
        self._channels: set[int] = set(self.settings.monitor_channel_ids or [])
        self._last_seen: dict[tuple[int, int], float] = {}
        self._decision_locks: WeakValueDictionary[tuple[int, int], asyncio.Lock] = (
            WeakValueDictionary()
        )
        self._warning_counts: dict[tuple[int, int], tuple[int, float]] = {}
        self._nudge_cycle: list[str] = []

    async def cog_load(self) -> None:  # type: ignore[override]
        # Merge channels persisted in Redis (if available).
        redis = getattr(self.bot, "redis", None)
        if redis is not None:
            try:
                members = await redis.smembers(MONITOR_CHANNELS_KEY)
                for m in members:
                    try:
                        self._channels.add(int(m))
                    except Exception:
                        continue
            except Exception:
                logger.exception("Failed to read monitor channels from Redis")
        logger.info("MonitorCog loaded watching channels=%s", self._channels)

    def is_channel_monitored(self, message: discord.Message) -> bool:
        """Return whether a message belongs to an owner-approved monitored channel."""

        channel_id = getattr(message.channel, "id", None)
        if channel_id in self._channels:
            return True

        # Threads should be considered monitored when their parent channel is monitored.
        parent = getattr(message.channel, "parent", None)
        parent_id = getattr(parent, "id", None)
        return parent_id in self._channels

    def _is_channel_monitored(self, message: discord.Message) -> bool:
        """Backward-compatible internal alias."""

        return self.is_channel_monitored(message)

    def monitored_channel_count(self, guild: discord.Guild) -> int:
        """Count configured channels that belong to the requested server."""

        return sum(
            1
            for channel_id in self._channels
            if guild.get_channel(channel_id) is not None or guild.get_thread(channel_id) is not None
        )

    def _playful_english_nudge(self) -> str:
        """Return every variation once before reshuffling the set."""

        if not self._nudge_cycle:
            self._nudge_cycle = list(ENGLISH_NUDGES)
            random.shuffle(self._nudge_cycle)
        return self._nudge_cycle.pop()

    @staticmethod
    def _detect_lang(content: str) -> str:
        # Explicit romanized-language signals must be checked before English
        # hints because a message can contain words from both languages.
        if _ROMANIZED_HINDI_HINT_RE.search(content):
            return "hi-latin"
        # Emoji and punctuation aren't language signals. Only route text with
        # actual non-ASCII letters (Devanagari, accented Latin, CJK, etc.).
        if any(ord(char) > 127 and char.isalpha() for char in content):
            return "non-en"

        words = _WORD_RE.findall(content)
        if not words:
            return "en"
        if _ENGLISH_CHAT_HINT_RE.search(content):
            return "en"

        # Very short ASCII chat is too ambiguous for statistical detection.
        # Defaulting it to English favors an occasional missed warning over
        # punishing a member who was already speaking English.
        if len(words) < 3:
            return "en"

        # Use langdetect only for longer ASCII messages and require high
        # confidence. Gemini performs a second verification before any reply.
        try:
            from langdetect import DetectorFactory, detect_langs

            DetectorFactory.seed = 0
            candidates = detect_langs(content)
            if candidates and candidates[0].prob >= 0.90:
                return candidates[0].lang
        except Exception:
            pass
        return "en"

    @staticmethod
    def _is_confirmed_non_english(response_text: str) -> bool:
        """Accept only Gemini's exact non-English classification."""

        return response_text.strip().casefold() == "non_english"

    async def _increment_warning(self, guild_id: int, user_id: int) -> int:
        """Increment a rolling warning counter, preferring Redis persistence."""

        redis = getattr(self.bot, "redis", None)
        if redis is not None:
            key = f"{MONITOR_WARNING_KEY_PREFIX}:{guild_id}:{user_id}"
            try:
                pipeline = redis.pipeline(transaction=True)
                pipeline.incr(key)
                pipeline.expire(key, WARNING_WINDOW_SECONDS)
                result = await pipeline.execute()
                return min(WARNING_LIMIT, int(result[0]))
            except Exception:
                logger.warning("Could not persist English warning counter", exc_info=True)

        key = (guild_id, user_id)
        now = time.monotonic()
        count, expires_at = self._warning_counts.get(key, (0, 0.0))
        if now >= expires_at:
            count = 0
        count = min(WARNING_LIMIT, count + 1)
        self._warning_counts[key] = (count, now + WARNING_WINDOW_SECONDS)
        return count

    async def _clear_warnings(self, guild_id: int, user_id: int) -> None:
        """Reset warnings after a successful timeout."""

        self._warning_counts.pop((guild_id, user_id), None)
        redis = getattr(self.bot, "redis", None)
        if redis is None:
            return
        try:
            await redis.delete(f"{MONITOR_WARNING_KEY_PREFIX}:{guild_id}:{user_id}")
        except Exception:
            logger.warning("Could not clear English warning counter", exc_info=True)

    @staticmethod
    async def _timeout_member(message: discord.Message) -> tuple[bool, str | None]:
        """Apply the configured timeout when Discord permissions and hierarchy allow it."""

        member = message.author
        guild = message.guild
        if not isinstance(member, discord.Member) or guild is None:
            return False, "I could not resolve that server member."
        if member.id == guild.owner_id or member.guild_permissions.administrator:
            return False, "Discord does not allow owners or administrators to be timed out."

        meyaya = guild.me
        if meyaya is None or not meyaya.guild_permissions.moderate_members:
            return False, "I need the Timeout Members permission to apply the 10-minute timeout."
        if meyaya.id != guild.owner_id and meyaya.top_role <= member.top_role:
            return False, "My highest role must be above this member's highest role."

        try:
            await member.timeout(
                TIMEOUT_DURATION,
                reason="Reached 3 confirmed English-only channel warnings.",
            )
        except discord.Forbidden:
            return False, "Discord refused the timeout. Check my role position and permissions."
        except discord.HTTPException:
            logger.exception("Discord timeout request failed user=%s guild=%s", member.id, guild.id)
            return False, "Discord could not apply the timeout right now."
        return True, None

    def _decision_lock(self, guild_id: int, user_id: int) -> asyncio.Lock:
        """Return a lock that exists only while this member has active work."""

        key = (guild_id, user_id)
        lock = self._decision_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._decision_locks[key] = lock
        return lock

    async def _process_non_english_candidate(
        self,
        message: discord.Message,
        content: str,
    ) -> None:
        """Verify and count one candidate while holding the member decision lock."""

        assert message.guild is not None
        key = (message.guild.id, message.author.id)
        now = time.monotonic()
        last = self._last_seen.get(key, 0.0)
        if now - last < MONITOR_COOLDOWN_SECONDS:
            return

        # The local detector only selects candidates. Gemini independently verifies
        # the language before a warning can affect the moderation counter.
        llm = self.bot.build_llm_provider()
        confirmed_non_english = False
        if llm is not None:
            try:
                system = build_moderation_instruction()
                resp = await llm.generate(
                    system,
                    content,
                    max_output_tokens=12,
                    timeout_seconds=8,
                )
                if resp is not None:
                    confirmed_non_english = self._is_confirmed_non_english(resp.text)
            except Exception:
                logger.exception("Gemini language verification failed")

        if not confirmed_non_english:
            # Silence is intentional for English, ambiguity, or verifier failure.
            return

        # Reserve the server-wide member cooldown before any further await. Other
        # messages queued on this member's lock will observe it and cannot add a
        # second warning from the same burst.
        self._last_seen[key] = time.monotonic()
        warning_count = await self._increment_warning(message.guild.id, message.author.id)
        timed_out = False
        timeout_error: str | None = None
        if warning_count >= WARNING_LIMIT:
            timed_out, timeout_error = await self._timeout_member(message)
            if timed_out:
                await self._clear_warnings(message.guild.id, message.author.id)

        if timed_out:
            consequence = "Warning **3/3** - timed out for **10 minutes**."
        elif warning_count >= WARNING_LIMIT:
            consequence = f"Warning **3/3** - {timeout_error}"
        else:
            consequence = (
                f"Warning **{warning_count}/{WARNING_LIMIT}** - warning 3 results in a "
                "10-minute timeout."
            )
        reply_text = f"{self._playful_english_nudge()}\n{consequence}"
        try:
            await message.reply(
                reply_text,
                mention_author=True,
                allowed_mentions=discord.AllowedMentions(
                    everyone=False,
                    roles=False,
                    users=False,
                    replied_user=True,
                ),
            )
        except Exception:
            logger.exception("Failed to send English-only warning")

    @commands.Cog.listener()
    @discord_context("moderation")
    async def on_message(self, message: discord.Message) -> None:
        moderation = self.bot.get_cog("ModerationCog")
        if moderation and await moderation.should_block(message):
            return
        # Ignore bot messages and DMs.
        if message.author is None or message.author.bot:
            return
        if message.guild is None:
            return

        channel_id = getattr(message.channel, "id", None)
        if channel_id is None:
            return
        if not self._is_channel_monitored(message):
            return

        content = (message.content or "").strip()
        if not content:
            return

        lang = self._detect_lang(content)

        if lang == "en" or lang.startswith("en"):
            # Nothing to do for English messages.
            return

        async with self._decision_lock(message.guild.id, message.author.id):
            await self._process_non_english_candidate(message, content)

    @commands.hybrid_command(
        name="monitor_add",
        description="Enforce the English-only rule in a channel.",
        with_app_command=True,
    )
    @commands.has_guild_permissions(manage_guild=True)
    @commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def monitor_add(self, ctx: commands.Context, channel: discord.abc.GuildChannel) -> None:
        """Add a channel (text or voice) to the monitored list."""
        cid = getattr(channel, "id", None)
        if cid is None or ctx.guild is None or getattr(getattr(channel, "guild", None), "id", None) != ctx.guild.id:
            await ctx.send("Choose a channel belonging to this server.")
            return
        redis = getattr(self.bot, "redis", None)
        try:
            if redis is not None:
                await redis.sadd(MONITOR_CHANNELS_KEY, cid)
            self._channels.add(int(cid))
            await ctx.send(
                embed=meyaya_embed(
                    "Language Monitor Updated",
                    f"Now enforcing the English-only rule in {channel.mention}.",
                    tone="success",
                    icon="🌐",
                )
            )
        except Exception:
            logger.exception("Failed to add channel to monitor set")
            await ctx.send("Failed to add channel to monitor list")

    @commands.hybrid_command(
        name="monitor_remove",
        description="Stop enforcing the English-only rule in a channel.",
        with_app_command=True,
    )
    @commands.has_guild_permissions(manage_guild=True)
    @commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def monitor_remove(
        self, ctx: commands.Context, channel: discord.abc.GuildChannel
    ) -> None:
        """Remove a channel from the monitored list."""
        cid = getattr(channel, "id", None)
        if cid is None or ctx.guild is None or getattr(getattr(channel, "guild", None), "id", None) != ctx.guild.id:
            await ctx.send("Choose a channel belonging to this server.")
            return
        redis = getattr(self.bot, "redis", None)
        try:
            if redis is not None:
                await redis.srem(MONITOR_CHANNELS_KEY, cid)
            self._channels.discard(int(cid))
            await ctx.send(
                embed=meyaya_embed(
                    "Language Monitor Updated",
                    f"Stopped watching {channel.mention}.",
                    tone="muted",
                    icon="🌐",
                )
            )
        except Exception:
            logger.exception("Failed to remove channel from monitor set")
            await ctx.send("Failed to remove channel from monitor list")

    @commands.hybrid_command(
        name="monitor_list",
        description="Show every channel with English-only monitoring enabled.",
        with_app_command=True,
    )
    @commands.has_guild_permissions(manage_guild=True)
    @commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def monitor_list(self, ctx: commands.Context) -> None:
        """List monitored channels."""
        if ctx.guild is None:
            await ctx.send("Use this command inside a server.")
            return
        channels = sorted(channel.id for channel in ctx.guild.channels if channel.id in self._channels)
        if not channels:
            await ctx.send("No channels are currently monitored in this server.")
            return
        mentions = "\n".join(f"- <#{channel_id}>" for channel_id in channels[:100])
        if len(channels) > 100:
            mentions += f"\n...and {len(channels) - 100} more in this server."
        await ctx.send(
            embed=meyaya_embed(
                "Monitored Channels",
                mentions,
                tone="info",
                icon="🌐",
            ),
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: MeyayaBot) -> None:
    await bot.add_cog(MonitorCog(bot))
