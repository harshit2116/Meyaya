"""Image-based Discord profile and aesthetic commands."""

from __future__ import annotations

import asyncio
from bot.utils.image_work import image_work
from io import BytesIO

import discord
from discord import app_commands
from discord.ext import commands

from bot.app import MeyayaBot
from bot.logging.telemetry import discord_context
from bot.services.profile_cards import (
    aura_card,
    callingcard_card,
    duostyle_card,
    palette_card,
    profilecheck_card,
)
from bot.services.profiles import ProfileService
from bot.services.profile_aesthetic import profilecheck_analysis


class ProfileStudioCog(commands.Cog):
    """Turn public Discord profile styling into collectible Meyaya cards."""

    def __init__(self, bot: MeyayaBot) -> None:
        self.bot = bot
        self.aesthetics = bot.build_profile_aesthetic_service()

    async def _member(self, ctx: commands.Context, member: discord.Member | None):
        if ctx.guild is None:
            await ctx.send("This command only works inside a server.", ephemeral=True)
            return None
        target = member or ctx.author
        if not isinstance(target, discord.Member):
            await ctx.send("I could not resolve that member.", ephemeral=True)
            return None
        await ctx.defer()
        return target

    @commands.hybrid_command(
        name="profilecheck",
        description="Score a member's avatar, banner, decoration, and overall profile look.",
    )
    @commands.cooldown(1, 12, commands.BucketType.member)
    @app_commands.describe(member="Member whose visible Discord profile should be reviewed")
    @discord_context("profile_studio")
    async def profilecheck(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
    ) -> None:
        target = await self._member(ctx, member)
        if target is None:
            return
        visual = await self.aesthetics.inspect(target)
        visual = await image_work(profilecheck_analysis, visual)
        rendered = await image_work(profilecheck_card, visual)
        await self._send_card(ctx, rendered, "meyaya-profile-check.png")

    @commands.hybrid_command(name="aura", description="Reveal a member's profile aura.")
    @commands.cooldown(1, 10, commands.BucketType.member)
    @app_commands.describe(member="Member whose profile aura should be revealed")
    @discord_context("profile_studio")
    async def aura(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
    ) -> None:
        target = await self._member(ctx, member)
        if target is None:
            return
        visual = await self.aesthetics.inspect(target)
        rendered = await image_work(aura_card, visual)
        await self._send_card(ctx, rendered, "meyaya-aura.png")

    @commands.hybrid_command(
        name="palette", description="Build a palette from a member's profile colors."
    )
    @commands.cooldown(1, 8, commands.BucketType.member)
    @app_commands.describe(member="Member whose avatar and banner colors should be sampled")
    @discord_context("profile_studio")
    async def palette(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
    ) -> None:
        target = await self._member(ctx, member)
        if target is None:
            return
        visual = await self.aesthetics.inspect(target)
        rendered = await image_work(palette_card, visual)
        await self._send_card(ctx, rendered, "meyaya-profile-palette.png")

    @commands.hybrid_command(
        name="duostyle",
        description="See how well two members' profile styles match.",
    )
    @commands.cooldown(1, 12, commands.BucketType.member)
    @app_commands.describe(first="First member", second="Second member")
    @discord_context("profile_studio")
    async def duostyle(
        self,
        ctx: commands.Context,
        first: discord.Member,
        second: discord.Member,
    ) -> None:
        if ctx.guild is None:
            await ctx.send("This command only works inside a server.", ephemeral=True)
            return
        if first.id == second.id:
            await ctx.send("Choose two different members for a duo check.", ephemeral=True)
            return
        await ctx.defer()
        left, right = await asyncio.gather(
            self.aesthetics.inspect(first),
            self.aesthetics.inspect(second),
        )
        rendered = await image_work(duostyle_card, left, right)
        await self._send_card(ctx, rendered, "meyaya-duo-style.png")

    @commands.hybrid_command(
        name="callingcard",
        description="Make a collectible card from a profile and Meyaya bond.",
    )
    @commands.cooldown(1, 12, commands.BucketType.member)
    @app_commands.describe(member="Member whose Meyaya calling card should be created")
    @discord_context("profile_studio")
    async def callingcard(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
    ) -> None:
        target = await self._member(ctx, member)
        if target is None:
            return
        async with self.bot.db_session() as session:
            summary = await ProfileService(session).build(target.id, ctx.guild.id)
        visual = await self.aesthetics.inspect(target)
        rendered = await image_work(
            callingcard_card,
            visual,
            nickname=summary.meyaya.nickname,
            relationship=summary.meyaya.relationship,
            titles=summary.titles,
        )
        await self._send_card(ctx, rendered, "meyaya-calling-card.png")

    @staticmethod
    async def _send_card(ctx: commands.Context, image: bytes, filename: str) -> None:
        await ctx.send(
            file=discord.File(BytesIO(image), filename=filename),
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: MeyayaBot) -> None:
    await bot.add_cog(ProfileStudioCog(bot))
