"""MonitorCog: monitor configured channels, translate non-English messages, and log context.

Behavior:
- Loads monitored channels from settings and Redis.
- Supports text channels and voice channel events.
- Detects non-English text and asks for English with a playful Meyaya tone.
"""

from __future__ import annotations

import logging
import random
import re
import time

import discord
from discord.ext import commands

from bot.app import MeyayaBot
from bot.config.settings import get_settings

logger = logging.getLogger(__name__)

MONITOR_CHANNELS_KEY = "monitor:channels"
# Cooldown in seconds per user per channel for translation replies
MONITOR_COOLDOWN_SECONDS = 25

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
    "Meyaya's language radar went beep - English, please 😼",
    "Quick Meyaya checkpoint: let's keep it in English, please ✨",
    "English mode, pretty please? Meyaya wants everyone in the loop 💫",
    "I translated this one - use English next time so everyone can follow 😺",
    "Tiny language bonk from Meyaya: English in here, please 🔨",
    "Meyaya patrol reporting in: English chat, please 🫡",
    "Let's switch that to English so nobody gets left out 🌸",
    "Translation delivered! English for the next message, deal? 😸",
)


class MonitorCog(commands.Cog):
    def __init__(self, bot: MeyayaBot) -> None:
        self.bot = bot
        self.settings = get_settings()
        self._channels: set[int] = set(self.settings.monitor_channel_ids or [])
        self._last_seen: dict[tuple[int, int], float] = {}
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
        # Defaulting it to English favors an occasional missed translation over
        # publicly "correcting" a member who was already speaking English.
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
    def _extract_translation(response_text: str) -> str | None:
        """Accept only an explicitly classified non-English translation."""

        response = response_text.strip()
        if response.casefold() == "no_translation":
            return None
        prefix = "translation:"
        if not response.casefold().startswith(prefix):
            return None
        translation = response[len(prefix) :].strip()
        return translation or None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
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

        # Translation reply cooldown per-user per-channel.
        key = (channel_id, message.author.id)
        now = time.time()
        last = self._last_seen.get(key, 0)
        if now - last < MONITOR_COOLDOWN_SECONDS:
            return
        lang = self._detect_lang(content)

        if lang == "en" or lang.startswith("en"):
            # Nothing to do for English messages.
            return
        # The local detector only selects candidates. Gemini must independently
        # confirm that the message is non-English before the bot addresses anyone.
        gemini = self.bot.build_gemini_service()
        translated = None
        if gemini is not None:
            try:
                system = (
                    "You are a strict language gate and translator for a Discord server. "
                    "Decide whether the message is predominantly English. Treat English slang, "
                    "abbreviations, misspellings, and casual or incorrect grammar as English; never "
                    "rewrite or correct them. For English, output exactly NO_TRANSLATION. Only when "
                    "the message is genuinely non-English, output exactly TRANSLATION: followed by a "
                    "natural English translation. For mixed-language messages, translate only when "
                    "the meaningful content is predominantly non-English. Add no explanation."
                )
                resp = await gemini.generate(
                    system,
                    content,
                    max_output_tokens=96,
                    timeout_seconds=8,
                )
                if resp is not None:
                    translated = self._extract_translation(resp.text)
            except Exception:
                logger.exception("Gemini translation failed")

        if translated is None:
            # Silence is intentional: the message was English/ambiguous, or the
            # verifier was unavailable. Don't accuse the member on uncertainty.
            return

        self._last_seen[key] = now

        # Reply with translation + playful English nudge in Meyaya style.
        reply_text = f"{self._playful_english_nudge()}\nTranslation: {translated}"
        try:
            await message.reply(reply_text)
        except Exception:
            logger.exception("Failed to send translation reply")

    @commands.hybrid_command(name="monitor_add", with_app_command=True)
    @commands.has_guild_permissions(manage_guild=True)
    async def monitor_add(self, ctx: commands.Context, channel: discord.abc.GuildChannel) -> None:
        """Add a channel (text or voice) to the monitored list."""
        cid = getattr(channel, "id", None)
        if cid is None:
            await ctx.send("Invalid channel")
            return
        redis = getattr(self.bot, "redis", None)
        try:
            if redis is not None:
                await redis.sadd(MONITOR_CHANNELS_KEY, cid)
            self._channels.add(int(cid))
            await ctx.send(f"Added channel {channel.mention} to monitor list")
        except Exception:
            logger.exception("Failed to add channel to monitor set")
            await ctx.send("Failed to add channel to monitor list")

    @commands.hybrid_command(name="monitor_remove", with_app_command=True)
    @commands.has_guild_permissions(manage_guild=True)
    async def monitor_remove(
        self, ctx: commands.Context, channel: discord.abc.GuildChannel
    ) -> None:
        """Remove a channel from the monitored list."""
        cid = getattr(channel, "id", None)
        if cid is None:
            await ctx.send("Invalid channel")
            return
        redis = getattr(self.bot, "redis", None)
        try:
            if redis is not None:
                await redis.srem(MONITOR_CHANNELS_KEY, cid)
            self._channels.discard(int(cid))
            await ctx.send(f"Removed channel {channel.mention} from monitor list")
        except Exception:
            logger.exception("Failed to remove channel from monitor set")
            await ctx.send("Failed to remove channel from monitor list")

    @commands.hybrid_command(name="monitor_list", with_app_command=True)
    @commands.has_guild_permissions(manage_guild=True)
    async def monitor_list(self, ctx: commands.Context) -> None:
        """List monitored channels."""
        if not self._channels:
            await ctx.send("No channels are currently monitored.")
            return
        mentions = []
        for cid in sorted(self._channels):
            mentions.append(f"<#{cid}>")
        await ctx.send("Monitored channels:\n" + "\n".join(mentions))

async def setup(bot: MeyayaBot) -> None:
    await bot.add_cog(MonitorCog(bot))
