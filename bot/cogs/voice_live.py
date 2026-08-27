"""Voice Live commands and guild session lifecycle for Gemini VC chat."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.app import MeyayaBot
from bot.services.voice_session import VoiceChatSession

logger = logging.getLogger(__name__)


class VoiceLiveCog(commands.Cog):
    def __init__(self, bot: MeyayaBot) -> None:
        self.bot = bot
        self._sessions: dict[int, VoiceChatSession] = {}

    async def cog_unload(self) -> None:
        for session in list(self._sessions.values()):
            await session.close(reason="voice cog unload")
        self._sessions.clear()

    def _get_guild_session(self, guild_id: int) -> VoiceChatSession:
        if guild_id not in self._sessions:
            self._sessions[guild_id] = VoiceChatSession(self.bot, guild_id)
        return self._sessions[guild_id]

    @app_commands.command(
        name="join", description="Join your voice channel and start Gemini live chat"
    )
    async def join(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or interaction.user is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "Could not resolve your member profile.", ephemeral=True
            )
            return

        if member.voice is None or member.voice.channel is None:
            await interaction.response.send_message(
                "Join a voice channel first, then run `/join`.", ephemeral=True
            )
            return

        channel = member.voice.channel
        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            await interaction.response.send_message(
                "Unsupported channel type for voice chat.", ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True, ephemeral=True)
        session = self._get_guild_session(interaction.guild.id)

        try:
            await session.connect_and_start(channel)
        except Exception as exc:
            logger.exception("Failed to start VC live session")
            await interaction.followup.send(f"Could not start voice chat: {exc}", ephemeral=True)
            return

        await interaction.followup.send(
            f"Joined {channel.mention} with Gemini Live voice `{self.bot.settings.gemini_voice}`.",
            ephemeral=True,
        )

    @app_commands.command(name="leave", description="Leave voice chat and stop Gemini live chat")
    async def leave(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        session = self._sessions.get(interaction.guild.id)
        if session is None:
            await interaction.response.send_message(
                "No active voice chat session in this server.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        await session.close(reason=f"/leave requested by user {interaction.user.id}")
        self._sessions.pop(interaction.guild.id, None)
        await interaction.followup.send(
            "Voice chat session stopped and disconnected.", ephemeral=True
        )

    @app_commands.command(
        name="voicecheck",
        description="Verify Gemini audio playback in the active voice channel",
    )
    async def voicecheck(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        session = self._sessions.get(interaction.guild.id)
        if session is None:
            await interaction.response.send_message(
                "Start voice chat with `/join` first.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        try:
            await session.run_voice_check()
        except Exception as exc:
            logger.exception("Voice playback check failed")
            await interaction.followup.send(f"Voice check failed: {exc}", ephemeral=True)
            return

        await interaction.followup.send(
            "Voice check requested; listen for Meyaya in the channel.", ephemeral=True
        )

    @app_commands.command(
        name="voicediag",
        description="Show live voice receive, DAVE, Gemini, and playback counters",
    )
    async def voicediag(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        session = self._sessions.get(interaction.guild.id)
        if session is None:
            await interaction.response.send_message(
                "Start voice chat with `/join` first.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"```text\n{session.diagnostic_report()}\n```",
            ephemeral=True,
        )

    @app_commands.command(name="voice", description="Show or change Gemini live voice")
    @app_commands.describe(name="Optional voice name, e.g. Kore, Leda, Aoede")
    async def voice(self, interaction: discord.Interaction, name: str | None = None) -> None:
        if name is None:
            await interaction.response.send_message(
                f"Current live voice is `{self.bot.settings.gemini_voice}`. "
                "Set `GEMINI_VOICE` in `.env` and restart to change globally.",
                ephemeral=True,
            )
            return

        # Runtime override for this process.
        self.bot.settings.gemini_voice = name.strip()
        await interaction.response.send_message(
            f"Voice updated for new sessions: `{self.bot.settings.gemini_voice}`.",
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
        session = self._sessions.get(guild.id)
        if session is None:
            return

        if after.channel is None:
            await session.close(reason="Discord reported bot voice disconnect")
            self._sessions.pop(guild.id, None)


async def setup(bot: MeyayaBot) -> None:
    await bot.add_cog(VoiceLiveCog(bot))
