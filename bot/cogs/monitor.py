"""MonitorCog: monitor configured channels, translate non-English messages, and log context.

Behavior:
- Loads monitored channels from settings and Redis.
- Supports text channels and voice channel events.
- Stores monitored message activity in chat memory when possible.
- Detects non-English text and asks for English with a playful Meyaya tone.
"""

from __future__ import annotations

import logging
import time
import re
from typing import Iterable

import discord
from discord.ext import commands

from bot.app import MeyayaBot
from bot.config.settings import get_settings

logger = logging.getLogger(__name__)

MONITOR_CHANNELS_KEY = "monitor:channels"
# Cooldown in seconds per user per channel for translation replies
MONITOR_COOLDOWN_SECONDS = 25

# Simple fallback language heuristic: consider message non-ASCII-heavy as non-English
_NON_ASCII_RE = re.compile(r"[^\x00-\x7F]")
_ROMANIZED_HINDI_HINT_RE = re.compile(
    r"\b(kya|kaise|kaisa|kaisi|haan|han|nahi|nahin|acha|accha|aur|haal|chaal|bhai|yaar|namaste|shukriya)\b",
    re.IGNORECASE,
)


class MonitorCog(commands.Cog):
    def __init__(self, bot: MeyayaBot) -> None:
        self.bot = bot
        self.settings = get_settings()
        self._channels: set[int] = set(self.settings.monitor_channel_ids or [])
        self._last_seen: dict[tuple[int, int], float] = {}

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

    def _is_channel_monitored(self, message: discord.Message) -> bool:
        channel_id = getattr(message.channel, "id", None)
        if channel_id in self._channels:
            return True

        # Threads should be considered monitored when their parent channel is monitored.
        parent = getattr(message.channel, "parent", None)
        parent_id = getattr(parent, "id", None)
        return parent_id in self._channels

    @staticmethod
    def _playful_english_nudge() -> str:
        lines = [
            "Meyaya is on duty, so let's keep chat in English please 😼",
            "Tiny language check from Meyaya: English mode, pretty please ✨",
            "Meyaya patrol says: English chat unlocked, let's gooo 💫",
            "I can translate this one, but speak English next so I can yap faster 😺",
        ]
        # time-based variation without importing random
        idx = int(time.time()) % len(lines)
        return lines[idx]

    @staticmethod
    def _detect_lang(content: str) -> str:
        # Prefer langdetect when available.
        try:
            from langdetect import detect

            detected = detect(content)
            if detected:
                return detected
        except Exception:
            pass

        # Fallback heuristics.
        if _NON_ASCII_RE.search(content):
            return "non-en"
        if _ROMANIZED_HINDI_HINT_RE.search(content):
            return "hi-latin"
        return "en"

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

        # Log monitored message activity to short-term memory whenever possible.
        try:
            chat_mem = self.bot.build_chat_memory_service()
            if chat_mem is not None:
                await chat_mem.append_turn(
                    channel_id,
                    content,
                    "",
                    speaker_label=self._speaker_label(message.author),
                )
        except Exception:
            logger.exception("Failed to persist monitored message to chat memory")

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
        self._last_seen[key] = now

        # We detected a non-English message. Attempt translation using a smaller/faster request.
        gemini = self.bot.build_gemini_service()
        translated = None
        if gemini is not None:
            try:
                system = (
                    "You are a concise translation assistant. Translate the user message into natural English. "
                    "Return only the translated text, no explanations."
                )
                resp = await gemini.generate(
                    system,
                    content,
                    max_output_tokens=96,
                    timeout_seconds=8,
                )
                if resp is not None:
                    translated = resp.text.strip()
            except Exception:
                logger.exception("Gemini translation failed")

        if translated is None:
            # Last-resort note.
            try:
                await message.reply(
                    "I detected a non-English message and couldn't translate it right now."
                )
            except Exception:
                logger.exception("Failed replying to message with translation-unavailable notice")
            return

        # Reply with translation + playful English nudge in Meyaya style.
        reply_text = f"{self._playful_english_nudge()}\nTranslation: {translated}"
        try:
            await message.reply(reply_text)
        except Exception:
            logger.exception("Failed to send translation reply")

        # Persist the message and (if available) translation to chat memory when possible
        try:
            chat_mem = self.bot.build_chat_memory_service()
            if chat_mem is not None:
                await chat_mem.append_turn(
                    message.channel.id,
                    content,
                    translated,
                    speaker_label=self._speaker_label(message.author),
                )
        except Exception:
            logger.exception("Failed to persist message to chat memory")

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

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        # Log voice joins/leaves into chat memory (if the voice channel is monitored).
        vc_before = before.channel.id if before and before.channel else None
        vc_after = after.channel.id if after and after.channel else None
        try:
            # When a user joins a monitored voice channel, persist an event.
            if vc_after and int(vc_after) in self._channels:
                chat_mem = self.bot.build_chat_memory_service()
                if chat_mem is not None:
                    text = f"[Voice] {member.display_name} joined voice channel"
                    await chat_mem.append_turn(
                        vc_after,
                        text,
                        "",
                        speaker_label=self._speaker_label(member),
                    )
            if vc_before and int(vc_before) in self._channels and (vc_after != vc_before):
                chat_mem = self.bot.build_chat_memory_service()
                if chat_mem is not None:
                    text = f"[Voice] {member.display_name} left voice channel"
                    await chat_mem.append_turn(
                        vc_before,
                        text,
                        "",
                        speaker_label=self._speaker_label(member),
                    )
        except Exception:
            logger.exception("Failed to log voice state change to chat memory")

    @staticmethod
    def _speaker_label(author: discord.abc.User) -> str:
        handle = getattr(author, "name", None) or str(author)
        return (
            f'Discord user display name "{author.display_name}", handle "@{handle}", ID {author.id}'
        )


async def setup(bot: MeyayaBot) -> None:
    await bot.add_cog(MonitorCog(bot))
