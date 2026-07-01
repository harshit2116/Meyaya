"""Daily fun slash commands."""

from __future__ import annotations

from datetime import date
from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from bot.app import MeyayaBot
from bot.services.daily import DailyService


class DailyCog(commands.Cog):
    """Commands for daily IQ and daily winners."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="dailyiq", description="Show a daily IQ score for a member.")
    @app_commands.describe(member="Member to score; defaults to you.")
    async def dailyiq(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command only works inside a server.", ephemeral=True)
            return
        target = member or interaction.user
        bot = cast(MeyayaBot, interaction.client)
        async with bot.db_session() as session:
            service = DailyService(session)
            score = await service.iq_score(interaction.guild.id, target.id, date.today())
            embed = discord.Embed(
                title="Daily IQ Certificate",
                description=f"{target.mention} scored **{score} IQ** today.",
                color=0x5C7CFA,
            )
            embed.set_thumbnail(url=str(target.display_avatar.url))
            await interaction.response.send_message(embed=embed)

    @app_commands.command(name="dailydumbest", description="Choose the dumbest member of the day.")
    async def dailydumbest(self, interaction: discord.Interaction) -> None:
        await self._daily_winner(interaction, "dumbest", "Dumbest Person of the Day", 0xFF6B6B)

    @app_commands.command(name="dailysmartest", description="Choose the smartest member of the day.")
    async def dailysmartest(self, interaction: discord.Interaction) -> None:
        await self._daily_winner(interaction, "smartest", "Smartest Person of the Day", 0x4D96FF)

    @app_commands.command(name="dailyclown", description="Choose the clown of the day.")
    async def dailyclown(self, interaction: discord.Interaction) -> None:
        await self._daily_winner(interaction, "clown", "Clown of the Day", 0xF9C74F)

    async def _daily_winner(self, interaction: discord.Interaction, kind: str, title: str, color: int) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command only works inside a server.", ephemeral=True)
            return
        candidates = [member.id for member in interaction.guild.members if not member.bot]
        if not candidates:
            await interaction.response.send_message("No eligible members were found.", ephemeral=True)
            return
        bot = cast(MeyayaBot, interaction.client)
        async with bot.db_session() as session:
            service = DailyService(session)
            winner_id = await service.daily_winner(interaction.guild.id, date.today(), kind, sorted(candidates))
            winner = interaction.guild.get_member(winner_id)
            winner_mention = winner.mention if winner else f"<@{winner_id}>"
            embed = discord.Embed(title=title, description=f"Today's pick is {winner_mention}.", color=color)
            if winner is not None:
                embed.set_thumbnail(url=str(winner.display_avatar.url))
            await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    """Install the daily commands cog."""

    await bot.add_cog(DailyCog(bot))
