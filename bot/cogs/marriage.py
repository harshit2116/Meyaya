"""Consent-first marriage, status, vow, and divorce commands."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.app import MeyayaBot
from bot.services.marriage import PendingProposalError, PendingProposalRegistry
from bot.utils.embeds import meyaya_embed
from bot.views.marriage import DivorceConfirmationView, MarriageProposalView

MAX_VOW_LENGTH = 500


class MarriageCog(commands.Cog):
    """Manage Meyaya marriages with explicit consent and safe confirmation."""

    def __init__(self, bot: MeyayaBot) -> None:
        self.bot = bot
        self.pending = PendingProposalRegistry()

    @commands.hybrid_command(name="marry", description="Propose marriage to another member.")
    @app_commands.describe(user="Member you want to propose to")
    async def marry(self, ctx: commands.Context, user: discord.Member) -> None:
        if ctx.interaction is not None:
            await ctx.defer()
        content, embed, view = await self._build_proposal(ctx.author, user)
        message = await ctx.send(
            content=content,
            embed=embed,
            view=view or discord.utils.MISSING,
            allowed_mentions=discord.AllowedMentions(users=True),
        )
        if view is not None:
            view.message = message

    @commands.hybrid_command(name="marriage", description="Show a member's marriage status.")
    @app_commands.describe(member="Member to inspect; defaults to you")
    async def marriage(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
    ) -> None:
        target = member or ctx.author
        async with self.bot.db_session() as session:
            summary = await self.bot.build_marriage_service(session).get_summary(target.id)

        if summary is None:
            await ctx.send(f"{target.mention} is not married in the Meyaya universe.")
            return

        partner = ctx.guild.get_member(summary.partner_id) if ctx.guild is not None else None
        partner_name = partner.display_name if partner is not None else f"User {summary.partner_id}"
        embed = meyaya_embed(
            f"{target.display_name}'s Marriage",
            f"## {target.mention} + <@{summary.partner_id}>",
            icon="💞",
        )
        embed.add_field(name="Partner", value=partner_name, inline=True)
        embed.add_field(
            name="Together",
            value=f"**{summary.days_together} day{'s' if summary.days_together != 1 else ''}**",
            inline=True,
        )
        embed.add_field(
            name="Married on",
            value=f"<t:{int(summary.married_at.timestamp())}:D>",
            inline=False,
        )
        embed.add_field(
            name="Next anniversary",
            value=(
                f"<t:{int(summary.next_anniversary.timestamp())}:D> "
                f"- {summary.days_until_anniversary} day"
                f"{'s' if summary.days_until_anniversary != 1 else ''} away"
            ),
            inline=False,
        )
        embed.set_thumbnail(url=str(target.display_avatar.url))
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @commands.hybrid_command(
        name="renewvows",
        description="Write a new vow to your current spouse.",
    )
    @app_commands.describe(vow="Your vow, up to 500 characters")
    async def renewvows(self, ctx: commands.Context, *, vow: str) -> None:
        clean_vow = " ".join(vow.split())[:MAX_VOW_LENGTH]
        if not clean_vow:
            await ctx.send("Write a vow first.")
            return
        async with self.bot.db_session() as session:
            summary = await self.bot.build_marriage_service(session).get_summary(ctx.author.id)
        if summary is None:
            await ctx.send("You need to be married before renewing your vows.")
            return

        safe_vow = discord.utils.escape_mentions(clean_vow)
        embed = meyaya_embed(
            "Vows Renewed",
            (
                f"{ctx.author.mention} renewed their vows to <@{summary.partner_id}>.\n\n"
                f"> {safe_vow}\n\n"
                f"Together for **{summary.days_together} day"
                f"{'s' if summary.days_together != 1 else ''}**."
            ),
            tone="soft",
            icon="💌",
        )
        embed.set_thumbnail(url=str(ctx.author.display_avatar.url))
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @commands.hybrid_command(
        name="divorce",
        description="Request a confirmed divorce from your current spouse.",
    )
    async def divorce(self, ctx: commands.Context) -> None:
        async with self.bot.db_session() as session:
            summary = await self.bot.build_marriage_service(session).get_summary(ctx.author.id)
        if summary is None:
            await ctx.send("You are not married to anyone right now.")
            return

        embed = meyaya_embed(
            "Confirm Divorce",
            (
                f"This will end the marriage between {ctx.author.mention} and "
                f"<@{summary.partner_id}>.\n\nThis cannot be undone without a new proposal."
            ),
            tone="danger",
            icon="💔",
        )
        view = DivorceConfirmationView(
            self.bot,
            ctx.author.id,
            summary.partner_id,
            summary.marriage_id,
        )
        view.message = await ctx.send(
            embed=embed,
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def _build_proposal(
        self,
        proposer: discord.abc.User,
        target: discord.abc.User,
    ) -> tuple[str | None, discord.Embed | None, MarriageProposalView | None]:
        """Build the same proposal flow for commands and validated natural actions."""

        if proposer.id == target.id:
            return "You cannot propose to yourself.", None, None
        if target.bot:
            return "Bots are not eligible for Meyaya marriage.", None, None

        try:
            await self.pending.reserve(proposer.id, target.id)
        except PendingProposalError as exc:
            return str(exc), None, None

        async with self.bot.db_session() as session:
            service = self.bot.build_marriage_service(session)
            occupied = await service.married_user_ids(proposer.id, target.id)
            if proposer.id in occupied:
                await self.pending.release(proposer.id, target.id)
                return "You are already married. Use `/marriage` to view it.", None, None
            if target.id in occupied:
                await self.pending.release(proposer.id, target.id)
                return f"{target.display_name} is already married.", None, None

        embed = meyaya_embed(
            "A Meyaya Marriage Proposal",
            (
                f"## {proposer.mention} + {target.mention}\n"
                f"{proposer.display_name} is asking {target.display_name} to get married.\n\n"
                "Only the person receiving the proposal can answer."
            ),
            icon="💍",
        )
        embed.set_thumbnail(url=str(target.display_avatar.url))
        view = MarriageProposalView(
            self.bot,
            proposer.id,
            target.id,
            self.pending,
        )
        return target.mention, embed, view


async def setup(bot: MeyayaBot) -> None:
    await bot.add_cog(MarriageCog(bot))
