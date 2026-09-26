"""Voice Live commands and guild session lifecycle for Gemini VC chat."""

from __future__ import annotations

import asyncio
import logging
import time
from weakref import WeakValueDictionary

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.app import MeyayaBot
from bot.data.voices import GEMINI_LIVE_VOICES, canonical_voice_name
from bot.services.voice_session import VoiceChatSession
from bot.services.chat_blacklist import acknowledge_silently
from bot.views.voice_picker import VoicePicker
from bot.services.ai_guard import AILimitReached
from bot.utils.embeds import meyaya_embed

logger = logging.getLogger(__name__)


class VoiceLiveCog(commands.Cog):
    def __init__(self, bot: MeyayaBot) -> None:
        self.bot = bot
        self._sessions: dict[int, VoiceChatSession] = {}
        self._lifecycle_locks: WeakValueDictionary[int, asyncio.Lock] = WeakValueDictionary()
        self._voice_overrides: dict[int, str] = {}
        self._empty_since = {}

    async def cog_load(self):
        self._empty_watch.start()

    @tasks.loop(seconds=15)
    async def _empty_watch(self):
        await self._check_empty_sessions()

    @_empty_watch.before_loop
    async def _before_empty_watch(self):
        await self.bot.wait_until_ready()

    async def _check_empty_sessions(self):
        for guild_id, session in list(self._sessions.items()):
            channel = getattr(session.voice_client, "channel", None)
            if channel is None or any(not member.bot for member in channel.members):
                self._empty_since.pop(guild_id, None)
                continue
            marker, since = self._empty_since.get(guild_id, (None, 0))
            identity = (session, channel.id)
            if marker != identity:
                self._empty_since[guild_id] = (identity, time.monotonic())
                continue
            if time.monotonic() - since < 180:
                continue
            async with self._lifecycle_lock(guild_id):
                if self._sessions.get(guild_id) is not session or any(
                    not member.bot for member in channel.members
                ):
                    self._empty_since.pop(guild_id, None)
                    continue
                try:
                    await session.close(reason="channel empty for 3 minutes")
                except Exception:
                    logger.exception("Automatic voice disconnect failed guild=%s", guild_id)
                    continue
                self._sessions.pop(guild_id, None)
                self._empty_since.pop(guild_id, None)
        for guild_id in set(self._empty_since) - self._sessions.keys():
            self._empty_since.pop(guild_id, None)

    async def cog_unload(self) -> None:
        self._empty_watch.cancel()
        self._empty_since.clear()
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
        name="join", description="Join your voice channel and start talking with Meyaya."
    )
    @commands.guild_only()
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
            except AILimitReached as error:
                await session.close(reason="voice safety limit")
                self._sessions.pop(ctx.guild.id, None)
                await ctx.send(str(error), ephemeral=True)
                return
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

    @commands.hybrid_command(name="leave", description="End voice chat and disconnect Meyaya.")
    @commands.guild_only()
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
        description="Check whether Meyaya can speak in the current voice channel.",
    )
    @commands.guild_only()
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

    @commands.hybrid_command(
        name="voice", description="Send a message and hear Meyaya reply in voice chat."
    )
    @commands.guild_only()
    @commands.cooldown(1, 8, commands.BucketType.member)
    async def voice(self, ctx: commands.Context, *, message: str) -> None:
        message = message.strip()
        if len(message) >= 2 and message[0] == message[-1] and message[0] in {'"', "'"}:
            message = message[1:-1].strip()
        if await self.bot.chat_blacklist.inspect(ctx.guild.id, ctx.author.id, message):
            await acknowledge_silently(ctx)
            return
        if not message or len(message) > 1000:
            await ctx.send("Send a message between 1 and 1,000 characters.", ephemeral=True)
            return
        session = self.active_session(ctx.guild.id)
        if session is None:
            await ctx.send(
                "Join a voice channel and use `join` first, then `voice <message>`.", ephemeral=True
            )
            return
        channel = getattr(getattr(ctx.author, "voice", None), "channel", None)
        if channel is None or channel.id != session.connected_channel_id:
            await ctx.send(
                "Join Meyaya's voice channel to send her a spoken-reply request.", ephemeral=True
            )
            return
        await ctx.defer(ephemeral=True)
        try:
            await asyncio.wait_for(session.reply_to_text(ctx.author.id, message), timeout=15)
        except (RuntimeError, TimeoutError):
            await ctx.send(
                "The voice connection isn't ready. Try again shortly, or reconnect with `leave` and `join`.",
                ephemeral=True,
            )
            return
        await ctx.send("Sent. Listen for Meyaya in voice chat.", ephemeral=True)

    @commands.hybrid_command(
        name="listen",
        description="Turn microphone listening on or off while staying in voice chat.",
    )
    @commands.guild_only()
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="On", value="on"),
            app_commands.Choice(name="Off", value="off"),
            app_commands.Choice(name="Status", value="status"),
        ]
    )
    async def listen(self, ctx: commands.Context, mode: str = "status"):
        mode = mode.lower().strip()
        if mode not in {"on", "off", "status"}:
            await ctx.send("Use `listen on`, `listen off`, or `listen status`.", ephemeral=True)
            return
        session = self.active_session(ctx.guild.id)
        if session is None:
            await ctx.send("Use `join` to start voice chat first.", ephemeral=True)
            return
        if not self._can_control_session(ctx.author, session):
            await ctx.send(
                "Join Meyaya's voice channel or ask a server manager to change listening.",
                ephemeral=True,
            )
            return
        await ctx.defer(ephemeral=True)
        if mode != "status":
            await session.set_listening(mode == "on")
        await ctx.send(
            f"Microphone listening is **{'on' if session.listening_enabled else 'off'}**. You can still use `voice <message>`.",
            ephemeral=True,
        )

    @commands.hybrid_command(name="voiceset", description="Show or change Meyaya's speaking voice.")
    @app_commands.describe(name="Optional voice name, e.g. Kore, Leda, Aoede")
    @commands.guild_only()
    async def voiceset(self, ctx: commands.Context, name: str | None = None) -> None:
        if ctx.guild is None:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        if not self._is_manager(ctx.author):
            await ctx.send("Only a server manager can change Meyaya's voice.", ephemeral=True)
            return
        if name is None:
            view = VoicePicker(self, ctx.author.id, ctx.guild.id)
            view.message = await ctx.send(
                f"Current voice: **{self._voice_for_guild(ctx.guild.id)}**\n"
                "Choose from 30 studio voices below. An active session will disconnect and reconnect in the same channel. "
                "Your microphone listening setting is preserved. Voice choices reset when the bot restarts.",
                view=view,
                ephemeral=True,
            )
            return
        if name.strip().casefold() != "default" and canonical_voice_name(name) is None:
            await ctx.send(
                "Unknown voice. Use `voiceset` to browse the voice menu.", ephemeral=True
            )
            return
        await ctx.defer(ephemeral=True)
        await ctx.send(await self.change_voice(ctx.guild.id, name), ephemeral=True)

    async def change_voice(self, guild_id: int, name: str) -> str:
        reset = name.strip().casefold() == "default"
        selected = self.bot.settings.gemini_voice if reset else canonical_voice_name(name)
        if selected is None:
            raise ValueError("Unsupported voice")
        async with self._lifecycle_lock(guild_id):
            if reset:
                self._voice_overrides.pop(guild_id, None)
            else:
                self._voice_overrides[guild_id] = selected
            previous = self._sessions.get(guild_id)
            if previous is None:
                return f"Voice set to **{selected}**. Use `join` when you are ready."
            channel = getattr(previous.voice_client, "channel", None)
            listening = previous.listening_enabled
            self._sessions.pop(guild_id, None)
            self._empty_since.pop(guild_id, None)
            await previous.close(reason="voice selection changed")
            if channel is None:
                return f"Voice set to **{selected}**. Use `join` to reconnect."
            replacement = self._get_guild_session(guild_id)
            replacement.listening_enabled = listening
            try:
                await asyncio.wait_for(replacement.connect_and_start(channel), timeout=60)
            except Exception:
                logger.exception("Voice selection reconnect failed guild=%s", guild_id)
                try:
                    await replacement.close(reason="voice selection reconnect failed")
                finally:
                    if self._sessions.get(guild_id) is replacement:
                        self._sessions.pop(guild_id, None)
                return f"Voice saved as **{selected}**, but reconnecting failed. Try `join` again."
            return f"Reconnected with **{selected}**. Microphone listening is **{'on' if listening else 'off'}**."

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
            if not member.bot and getattr(after, "channel", None) is not None:
                session = self._sessions.get(member.guild.id)
                if session and session.connected_channel_id == after.channel.id:
                    self._empty_since.pop(member.guild.id, None)
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
