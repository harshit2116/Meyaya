"""Profile slash command."""

from __future__ import annotations

from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from bot.app import MeyayaBot
from bot.services.profiles import ProfileService


class ProfileCog(commands.Cog):
    """Lightweight user profile command."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="profile", description="Show a member profile.")
    @app_commands.describe(member="Member to inspect; defaults to you.")
    async def profile(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command only works inside a server.", ephemeral=True)
            return

        target = member or interaction.user
        bot = cast(MeyayaBot, interaction.client)
        async with bot.db_session() as session:
            service = ProfileService(session)
            summary = await service.build(target.id)
            embed = discord.Embed(
                title=f"{target.display_name}'s Profile",
                color=0x8ECAE6,
                description=(
                    f"**Total interactions given:** {summary.total_given}\n"
                    f"**Total interactions received:** {summary.total_received}\n"
                    f"**Favorite interaction:** {summary.favorite_interaction or 'None yet'}\n"
                    f"**Most interacted-with member:** <@{summary.most_interacted_member_id}>"
                    if summary.most_interacted_member_id is not None
                    else "**Most interacted-with member:** None yet"
                ),
            )
            embed.set_thumbnail(url=str(target.display_avatar.url))
            await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    """Install the profile command cog."""

    await bot.add_cog(ProfileCog(bot))
