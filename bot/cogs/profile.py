"""Profile slash and text commands."""

from __future__ import annotations

from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from bot.app import MeyayaBot
from bot.services.profiles import ProfileService
from bot.utils.embeds import build_profile_embed


class ProfileCog(commands.Cog):
    """Lightweight user profile commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._text_command: commands.Command | None = None

    async def cog_load(self) -> None:
        """Register the written profile command."""

        self._text_command = self._build_text_profile()
        self.bot.add_command(self._text_command)

    def cog_unload(self) -> None:
        """Remove the written profile command."""

        if self._text_command is not None:
            self.bot.remove_command(self._text_command.name)

    @app_commands.command(name="profile", description="Show a member profile.")
    @app_commands.describe(member="Member to inspect; defaults to you.")
    async def profile(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command only works inside a server.",
                ephemeral=True,
            )
            return

        target = member or cast(discord.Member, interaction.user)
        bot = cast(MeyayaBot, interaction.client)

        async with bot.db_session() as session:
            service = ProfileService(session)
            summary = await service.build(target.id)

        await interaction.response.send_message(embed=build_profile_embed(target, summary))

    def _build_text_profile(self) -> commands.Command:
        async def callback(
            ctx: commands.Context[commands.Bot],
            member: discord.Member | None = None,
        ) -> None:
            if ctx.guild is None:
                await ctx.send("This command only works inside a server.")
                return

            target = member or cast(discord.Member, ctx.author)
            bot = cast(MeyayaBot, ctx.bot)

            async with bot.db_session() as session:
                service = ProfileService(session)
                summary = await service.build(target.id)

            await ctx.send(embed=build_profile_embed(target, summary))

        return commands.Command(
            callback,
            name="profile",
            help="Show a member profile.",
        )


async def setup(bot: commands.Bot) -> None:
    """Install the profile command cog."""

    await bot.add_cog(ProfileCog(bot))
