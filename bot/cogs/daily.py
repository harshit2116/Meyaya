"""Daily fun commands shared by slash, written prefix, and mention routing."""

from __future__ import annotations

from datetime import date
import logging
from random import choice

import discord
from discord import app_commands
from discord.ext import commands

from bot.app import MeyayaBot
from bot.services.daily import DailyService
from bot.utils.embeds import meyaya_embed

logger = logging.getLogger(__name__)

CLOWN_GIF_QUERIES = ("cat clown funny", "dog clown funny", "clown dog cat")
DAILY_ICONS = {
    "Daily IQ": "🧠",
    "Dumbest Person": "🫠",
    "Smartest Person": "✨",
    "Clown": "🤡",
}


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
        score = DailyService.iq_score(ctx.guild.id, target.id, date.today())
        await self._send_daily_embed(
            ctx,
            "Daily IQ",
            f"{target.mention} scored **{score} IQ** today.",
            (),
            0x5C7CFA,
        )

    @commands.hybrid_command(name="dumb", description="Choose the dumbest member of the day.")
    async def dumb(self, ctx: commands.Context) -> None:
        await self._daily_winner(ctx, "dumbest", "Dumbest Person", (), 0xFF6B6B)

    @commands.hybrid_command(name="smart", description="Choose the smartest member of the day.")
    async def smart(self, ctx: commands.Context) -> None:
        await self._daily_winner(ctx, "smartest", "Smartest Person", (), 0x4D96FF)

    @commands.hybrid_command(name="clown", description="Choose the clown of the day.")
    async def clown(self, ctx: commands.Context) -> None:
        await self._daily_winner(ctx, "clown", "Clown", CLOWN_GIF_QUERIES, 0xF9C74F)

    async def _daily_winner(
        self,
        ctx: commands.Context,
        kind: str,
        title: str,
        gif_queries: tuple[str, ...],
        color: int,
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
        async with self.bot.db_session() as session:
            winner_id = await DailyService(session).daily_winner(
                ctx.guild.id,
                date.today(),
                kind,
                candidates,
            )
        winner = ctx.guild.get_member(winner_id)
        winner_mention = winner.mention if winner else f"<@{winner_id}>"
        await self._send_daily_embed(
            ctx,
            title,
            f"Today's **{title.lower()}** is {winner_mention}.",
            gif_queries,
            color,
        )

    async def _send_daily_embed(
        self,
        ctx: commands.Context,
        title: str,
        message: str,
        gif_queries: tuple[str, ...],
        color: int,
    ) -> None:
        gif_url: str | None = None
        gif_service = self.bot.build_klipy_service() if gif_queries else None
        if gif_service is not None:
            try:
                result = await gif_service.random_gif(choice(gif_queries), prefer_anime=True)
                gif_url = result.url
            except Exception:
                logger.warning("Daily GIF lookup failed", exc_info=True)

        embed = meyaya_embed(
            title,
            message,
            color=color,
            icon=DAILY_ICONS.get(title, "🌸"),
        )
        if gif_url:
            embed.set_image(url=gif_url)
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: MeyayaBot) -> None:
    """Install the daily command family."""

    await bot.add_cog(DailyCog(bot))
