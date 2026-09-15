"""Voice Live commands and guild session lifecycle for Gemini VC chat."""

from __future__ import annotations

import asyncio
import logging
from weakref import WeakValueDictionary

import discord
from discord import app_commands
from discord.ext import commands

from bot.app import MeyayaBot
from bot.data.voices import GEMINI_LIVE_VOICES, canonical_voice_name
from bot.services.voice_session import VoiceChatSession
from bot.utils.embeds import meyaya_embed

logger = logging.getLogger(__name__)


class VoiceLiveCog(commands.Cog):
    def __init__(self, bot: MeyayaBot) -> None:
        self.bot = bot
        self._sessions: dict[int, VoiceChatSession] = {}
        self._lifecycle_locks: WeakValueDictionary[int, asyncio.Lock] = WeakValueDictionary()
        self._voice_overrides: dict[int, str] = {}

    async def cog_unload(self) -> None:
        for session in list(self._sessions.values()):
            await session.close(reason="voice cog unload")
        self._sessions.clear()

    def _lifecycle_lock(self, guild_id: int) -> asyncio.Lock:
        lock = self._lifecycle_locks.get(guild_id)
        if lock is None:
            lock = asyncio.Lock()
            self._lifecycle_locks[guild_id] = lock
        return lock

    def _voice_for_guild(self, guild_id: int) -> str:
        return self._voice_overrides.get(guild_id, self.bot.settings.gemini_voice)

    def _get_guild_session(self, guild_id: int) -> VoiceChatSession:
        if guild_id not in self._sessions:
            self._sessions[guild_id] = VoiceChatSession(
                self.bot,
                guild_id,
                voice_name=self._voice_for_guild(guild_id),
            )
        return self._sessions[guild_id]

    def active_session(self, guild_id: int) -> VoiceChatSession | None:
        """Expose one server's live session for administration diagnostics."""

        session = self._sessions.get(guild_id)
        return session if session is not None and session.is_active else None

    @staticmethod
    def _is_manager(member: discord.abc.User) -> bool:
        permissions = getattr(member, "guild_permissions", None)
        return bool(permissions and permissions.manage_guild)

    @classmethod
    def _can_control_session(
        cls,
        member: discord.abc.User,
        session: VoiceChatSession,
    ) -> bool:
        if cls._is_manager(member):
            return True
        voice = getattr(member, "voice", None)
        channel = getattr(voice, "channel", None)
        return channel is not None and channel.id == session.connected_channel_id

    @commands.hybrid_command(
        name="join", description="Join your voice channel and start Gemini live chat"
    )
    async def join(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        member = ctx.author
        if not isinstance(member, discord.Member):
            await ctx.send("Could not resolve your member profile.", ephemeral=True)
            return

        if member.voice is None or member.voice.channel is None:
            await ctx.send("Join a voice channel first, then use `join`.", ephemeral=True)
            return

        channel = member.voice.channel
        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            await ctx.send("Unsupported channel type for voice chat.", ephemeral=True)
            return

        await ctx.defer(ephemeral=True)
        async with self._lifecycle_lock(ctx.guild.id):
            existing = self._sessions.get(ctx.guild.id)
            if existing is not None and existing.is_active:
                if existing.connected_channel_id == channel.id:
                    await self._send_status(
                        ctx,
                        "Meyaya Is Already Listening",
                        f"I am already connected to **{channel.name}** and ready to speak.",
                        tone="info",
                        icon="🎙️",
                    )
                    return
                if not self._is_manager(member):
                    await self._send_status(
                        ctx,
                        "Voice Chat Already Active",
                        "Only a server manager can move Meyaya while another voice chat is active.",
                        tone="danger",
                        icon="🔒",
                    )
                    return
                await existing.close(reason=f"moved by manager {member.id}")
                self._sessions.pop(ctx.guild.id, None)
            elif existing is not None:
                await existing.close(reason="replacing inactive voice session")
                self._sessions.pop(ctx.guild.id, None)

            session = self._get_guild_session(ctx.guild.id)
            try:
                await session.connect_and_start(channel)
            except Exception:
                logger.exception("Failed to start VC live session")
                await session.close(reason="voice startup failed")
                if self._sessions.get(ctx.guild.id) is session:
                    self._sessions.pop(ctx.guild.id, None)
                await ctx.send(
                    "Could not start voice chat. Check the bot logs for the exact cause.",
                    ephemeral=True,
                )
                return

        await self._send_status(
            ctx,
            "Meyaya Is Listening",
            f"Connected to **{channel.name}** and ready to speak.",
            tone="success",
            icon="🎙️",
        )

    @commands.hybrid_command(name="leave", description="Leave voice chat and stop Gemini live chat")
    async def leave(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        await ctx.defer(ephemeral=True)
        async with self._lifecycle_lock(ctx.guild.id):
            session = self._sessions.get(ctx.guild.id)
            if session is None or not session.is_active:
                await ctx.send("No active voice chat session in this server.", ephemeral=True)
                return
            if not self._can_control_session(ctx.author, session):
                await ctx.send(
                    "Join Meyaya's current voice channel or ask a server manager to disconnect her.",
                    ephemeral=True,
                )
                return
            await session.close(reason=f"leave requested by user {ctx.author.id}")
            if self._sessions.get(ctx.guild.id) is session:
                self._sessions.pop(ctx.guild.id, None)
        await self._send_status(
            ctx,
            "Voice Chat Ended",
            "Disconnected safely. Call me again whenever you want to talk.",
            tone="muted",
            icon="🌙",
        )

    @commands.hybrid_command(
        name="voicecheck",
        description="Verify Gemini audio playback in the active voice channel",
    )
    async def voicecheck(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        await ctx.defer(ephemeral=True)
        async with self._lifecycle_lock(ctx.guild.id):
            session = self._sessions.get(ctx.guild.id)
            if session is None or not session.is_active:
                await ctx.send("Start voice chat with `join` first.", ephemeral=True)
                return
            if not self._can_control_session(ctx.author, session):
                await ctx.send(
                    "Join Meyaya's current voice channel before running a voice check.",
                    ephemeral=True,
                )
                return
            try:
                await asyncio.wait_for(session.run_voice_check(), timeout=15)
            except Exception:
                logger.exception("Voice playback check failed")
                await ctx.send(
                    "Voice check failed. Check the bot logs for the exact cause.",
                    ephemeral=True,
                )
                return

        await self._send_status(
            ctx,
            "Voice Check Sent",
            "Listen for Meyaya in the channel.",
            tone="info",
            icon="🔊",
        )

    @commands.hybrid_command(name="voice", description="Show or change Gemini live voice")
    @app_commands.describe(name="Optional voice name, e.g. Kore, Leda, Aoede")
    async def voice(self, ctx: commands.Context, name: str | None = None) -> None:
        if ctx.guild is None:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        current_voice = self._voice_for_guild(ctx.guild.id)
        if name is None:
            await self._send_status(
                ctx,
                "Meyaya's Voice",
                f"Current live voice for this server: **{current_voice}**\n"
                "Use `/voice name:<voice>` to change new sessions.",
                tone="soft",
                icon="🎶",
            )
            return

        if not self._is_manager(ctx.author):
            await ctx.send(
                "Only a server manager can change Meyaya's voice.",
                ephemeral=True,
            )
            return

        requested = name.strip()
        if requested.casefold() == "default":
            self._voice_overrides.pop(ctx.guild.id, None)
            selected = self.bot.settings.gemini_voice
        else:
            selected = canonical_voice_name(requested)
            if selected is None:
                choices = ", ".join(GEMINI_LIVE_VOICES)
                await ctx.send(
                    f"That voice is not supported. Available voices: {choices}",
                    ephemeral=True,
                )
                return
            self._voice_overrides[ctx.guild.id] = selected

        await self._send_status(
            ctx,
            "Voice Updated",
            f"New voice sessions in this server will use **{selected}**.",
            tone="success",
            icon="🎶",
        )

    @staticmethod
    async def _send_status(
        ctx: commands.Context,
        title: str,
        description: str,
        *,
        tone: str,
        icon: str,
    ) -> None:
        await ctx.send(
            embed=meyaya_embed(title, description, tone=tone, icon=icon),
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        # If bot is disconnected/moved unexpectedly, clean up the local session.
        if self.bot.user is None:
            return
        if member.id != self.bot.user.id:
            return

        guild = member.guild
        observed_session = self._sessions.get(guild.id)
        if observed_session is None:
            return

        if after.channel is None:
            async with self._lifecycle_lock(guild.id):
                # The event may belong to a session that a manager intentionally
                # replaced while this listener waited for the lifecycle lock.
                # Never let that stale disconnect tear down the replacement.
                if self._sessions.get(guild.id) is not observed_session:
                    return
                await observed_session.close(reason="Discord reported bot voice disconnect")
                if self._sessions.get(guild.id) is observed_session:
                    self._sessions.pop(guild.id, None)


async def setup(bot: MeyayaBot) -> None:
    await bot.add_cog(VoiceLiveCog(bot))
