"""Daily fun slash commands."""

from __future__ import annotations

from datetime import date
from random import choice
from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from bot.app import MeyayaBot
from bot.services.daily import DailyService

CLOWN_GIF_QUERIES = ("cat clown funny", "dog clown funny", "clown dog cat")


class DailyCog(commands.Cog):
    """Commands for daily IQ and daily winners."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._text_commands: list[commands.Command] = []

    async def cog_load(self) -> None:
        """Register written command versions of the daily commands."""

        commands_to_add = [
            self._build_text_iq(),
            self._build_text_dailywinners("dumb", "dumbest", "Dumbest Person", (), 0xFF6B6B),
            self._build_text_dailywinners("smart", "smartest", "Smartest Person", (), 0x4D96FF),
            self._build_text_dailywinners("clown", "clown", "Clown", CLOWN_GIF_QUERIES, 0xF9C74F),
        ]
        for command in commands_to_add:
            self.bot.add_command(command)
            self._text_commands.append(command)

    def cog_unload(self) -> None:
        """Remove the written commands when the cog unloads."""

        for command in self._text_commands:
            self.bot.remove_command(command.name)

    @app_commands.command(name="iq", description="Show a daily IQ score for a member.")
    @app_commands.describe(member="Member to score; defaults to you.")
    async def iq(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command only works inside a server.", ephemeral=True)
            return
        await interaction.response.defer()
        target = member or cast(discord.Member, interaction.user)
        bot = cast(MeyayaBot, interaction.client)
        score = DailyService.iq_score(interaction.guild.id, target.id, date.today())

        await self._send_daily_embed(
            bot,
            interaction,
            "Daily IQ",
            f"{target.mention} scored {score} IQ today.",
            (),
            0x5C7CFA,
        )

    @app_commands.command(name="dumb", description="Choose the dumbest member of the day.")
    async def dumb(self, interaction: discord.Interaction) -> None:
        await self._daily_winner(interaction, "dumbest", "Dumbest Person", (), 0xFF6B6B)

    @app_commands.command(name="smart", description="Choose the smartest member of the day.")
    async def smart(self, interaction: discord.Interaction) -> None:
        await self._daily_winner(interaction, "smartest", "Smartest Person", (), 0x4D96FF)

    @app_commands.command(name="clown", description="Choose the clown of the day.")
    async def clown(self, interaction: discord.Interaction) -> None:
        await self._daily_winner(interaction, "clown", "Clown", CLOWN_GIF_QUERIES, 0xF9C74F)

    def _build_text_iq(self) -> commands.Command:
        async def callback(
            ctx: commands.Context[commands.Bot],
            member: discord.Member | None = None,
        ) -> None:
            if ctx.guild is None:
                await ctx.send("This command only works inside a server.")
                return

            target = member or cast(discord.Member, ctx.author)
            bot = cast(MeyayaBot, ctx.bot)
            score = DailyService.iq_score(ctx.guild.id, target.id, date.today())

            await self._send_daily_embed(
                bot,
                ctx,
                "Daily IQ",
                f"{target.mention} scored {score} IQ today.",
                (),
                0x5C7CFA,
            )

        return commands.Command(callback, name="iq", help="Show a daily IQ score for a member.")

    def _build_text_dailywinners(
        self,
        name: str,
        kind: str,
        title: str,
        gif_queries: tuple[str, ...],
        color: int,
    ) -> commands.Command:
        async def callback(ctx: commands.Context[commands.Bot]) -> None:
            if ctx.guild is None:
                await ctx.send("This command only works inside a server.")
                return

            candidates = [member.id for member in ctx.guild.members if not member.bot]
            if not candidates:
                await ctx.send("No eligible members were found.")
                return

            bot = cast(MeyayaBot, ctx.bot)
            async with bot.db_session() as session:
                service = DailyService(session)
                winner_id = await service.daily_winner(ctx.guild.id, date.today(), kind, sorted(candidates))
            winner = ctx.guild.get_member(winner_id)
            winner_mention = winner.mention if winner else f"<@{winner_id}>"

            await self._send_daily_embed(
                bot,
                ctx,
                title,
                f"Today's {title.lower()} is {winner_mention}.",
                gif_queries,
                color,
            )

        return commands.Command(callback, name=name, help=f"Choose the {kind} member of the day.")

    async def _daily_winner(
        self,
        interaction: discord.Interaction,
        kind: str,
        title: str,
        gif_queries: tuple[str, ...],
        color: int,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command only works inside a server.", ephemeral=True)
            return
        await interaction.response.defer()
        candidates = [member.id for member in interaction.guild.members if not member.bot]
        if not candidates:
            await interaction.followup.send("No eligible members were found.", ephemeral=True)
            return
        bot = cast(MeyayaBot, interaction.client)
        async with bot.db_session() as session:
            service = DailyService(session)
            winner_id = await service.daily_winner(interaction.guild.id, date.today(), kind, sorted(candidates))
        winner = interaction.guild.get_member(winner_id)
        winner_mention = winner.mention if winner else f"<@{winner_id}>"

        await self._send_daily_embed(
            bot,
            interaction,
            title,
            f"Today's {title.lower()} is {winner_mention}.",
            gif_queries,
            color,
        )

    async def _send_daily_embed(
        self,
        bot: MeyayaBot,
        destination: discord.Interaction | commands.Context[commands.Bot],
        title: str,
        message: str,
        gif_queries: tuple[str, ...],
        color: int,
    ) -> None:
        gif_url: str | None = None
        if gif_queries:
            gif_service = bot.build_klipy_service()
            if gif_service is not None:
                gif_query = choice(gif_queries)
                gif_result = await gif_service.random_gif(gif_query, prefer_anime=True)
                gif_url = gif_result.url

        description = f"**{message}**"
        embed = discord.Embed(title=title, description=description, color=color)
        if gif_url:
            embed.set_image(url=gif_url)

        if isinstance(destination, discord.Interaction):
            await destination.followup.send(embed=embed)
            return

        await destination.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    """Install the daily commands cog."""

    await bot.add_cog(DailyCog(bot))
