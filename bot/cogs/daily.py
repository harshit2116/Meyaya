"""Daily fun commands shared by slash, written prefix, and mention routing."""

from __future__ import annotations

from datetime import date

import discord
from discord import app_commands
from discord.ext import commands

from bot.app import MeyayaBot
from bot.services.daily import DailyService


class DailyCog(commands.Cog):
    """Stable daily picks using one implementation for every command style."""

    def __init__(self, bot: MeyayaBot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="iq", description="Show a daily IQ score for a member.")
    @app_commands.describe(member="Member to score; defaults to you")
    async def iq(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
    ) -> None:
        if ctx.guild is None:
            await ctx.send("This command only works inside a server.")
            return
        target = member or ctx.author
        if not isinstance(target, discord.Member):
            await ctx.send("I could not identify that member.")
            return
        day = date.today()
        score = DailyService.iq_score(ctx.guild.id, target.id, day)
        name = discord.utils.escape_markdown(target.display_name)
        await ctx.send(
            f"IQ of {name} is {score} today.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @commands.hybrid_command(name="dumb", description="Choose the dumbest member of the day.")
    async def dumb(self, ctx: commands.Context) -> None:
        await self._daily_winner(ctx, "dumbest")

    @commands.hybrid_command(name="smart", description="Choose the smartest member of the day.")
    async def smart(self, ctx: commands.Context) -> None:
        await self._daily_winner(ctx, "smartest")

    @commands.hybrid_command(name="clown", description="Choose the clown of the day.")
    async def clown(self, ctx: commands.Context) -> None:
        await self._daily_winner(ctx, "clown")

    async def _daily_winner(
        self,
        ctx: commands.Context,
        kind: str,
    ) -> None:
        if ctx.guild is None:
            await ctx.send("This command only works inside a server.")
            return
        if ctx.interaction is not None:
            await ctx.defer()
        candidates = sorted(member.id for member in ctx.guild.members if not member.bot)
        if not candidates:
            await ctx.send("No eligible members were found.")
            return
        day = date.today()
        async with self.bot.db_session() as session:
            winner_id = await DailyService(session).daily_winner(
                ctx.guild.id,
                day,
                kind,
                candidates,
            )
        winner = ctx.guild.get_member(winner_id)
        name = discord.utils.escape_markdown(winner.display_name) if winner else f"<@{winner_id}>"
        label = {"dumbest": "dumbest member", "smartest": "smartest member", "clown": "clown"}[kind]
        await ctx.send(
            f"{name} is the {label} today.",
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: MeyayaBot) -> None:
    """Install the daily command family."""

    await bot.add_cog(DailyCog(bot))
