"""Unified member profile command."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.app import MeyayaBot
from bot.services.profiles import ProfileService
from bot.utils.embeds import build_profile_embed


class ProfileCog(commands.Cog):
    """Display Discord, social, marriage, and Meyaya relationship data."""

    def __init__(self, bot: MeyayaBot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="profile", description="Show a unified member profile.")
    @app_commands.describe(member="Member to inspect; defaults to you")
    async def profile(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
    ) -> None:
        if ctx.guild is None:
            await ctx.send("This command only works inside a server.", ephemeral=True)
            return
        if ctx.interaction is not None:
            await ctx.defer()

        target = member or ctx.author
        if not isinstance(target, discord.Member):
            await ctx.send("I could not resolve that member.")
            return
        async with self.bot.db_session() as session:
            summary = await ProfileService(session).build(target.id, ctx.guild.id)
        await ctx.send(
            embed=build_profile_embed(target, summary),
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: MeyayaBot) -> None:
    await bot.add_cog(ProfileCog(bot))
