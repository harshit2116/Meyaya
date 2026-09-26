"""Configured-channel entertainment court command."""

from __future__ import annotations

from bot.logging.telemetry import discord_context, event

import logging
import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from bot.app import MeyayaBot
from bot.models.court import CourtCase
from bot.services.court import (
    CourtClarification,
    CourtError,
    CourtJudge,
    CourtJudgement,
    CourtService,
    CourtStatus,
    CourtVerdict,
    court_case_lock,
    court_channel_error,
)
from bot.utils.embeds import meyaya_embed
from bot.views.court import (
    CourtClarificationView,
    CourtCollectionView,
    CourtInvitationView,
    build_court_embed,
)

logger = logging.getLogger(__name__)


class CourtCog(commands.Cog):
    """Run harmless, persistent Meyaya court cases in one configured channel."""

    def __init__(self, bot: MeyayaBot) -> None:
        self.bot = bot
        self.judge = CourtJudge(bot.build_llm_provider())

    @commands.hybrid_command(
        name="setcourt",
        description="Set this channel as the server's Meyaya court.",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def setcourt(self, ctx: commands.Context) -> None:
        if ctx.guild is None or ctx.channel is None:
            await ctx.send("Court configuration only works inside a server.")
            return
        if not self._can_manage_server(ctx.author):
            await ctx.send(
                "You need the Manage Server permission to configure Meyaya Court.",
                ephemeral=ctx.interaction is not None,
            )
            return

        async with self.bot.db_session() as session:
            service = CourtService(session)
            previous = await service.configured_channel(
                ctx.guild.id,
                self.bot.settings.court_channel_id,
            )
            await service.set_channel(ctx.guild.id, ctx.channel.id, ctx.author.id)

        if previous is not None and previous != ctx.channel.id:
            description = f"Meyaya Court moved from <#{previous}> to <#{ctx.channel.id}>."
        elif previous == ctx.channel.id:
            description = f"Meyaya Court was already configured in <#{ctx.channel.id}>."
        else:
            description = f"Meyaya Court is now configured in <#{ctx.channel.id}>."
        await ctx.send(
            embed=meyaya_embed(
                "Court Channel Configured",
                description,
                tone="success",
                icon="⚖️",
            ),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @commands.hybrid_command(
        name="removecourt",
        description="Disable Meyaya Court for this server.",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def removecourt(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            await ctx.send("Court configuration only works inside a server.")
            return
        if not self._can_manage_server(ctx.author):
            await ctx.send(
                "You need the Manage Server permission to configure Meyaya Court.",
                ephemeral=ctx.interaction is not None,
            )
            return

        async with self.bot.db_session() as session:
            service = CourtService(session)
            previous = await service.configured_channel(
                ctx.guild.id,
                self.bot.settings.court_channel_id,
            )
            await service.remove_channel(ctx.guild.id, ctx.author.id)

        description = (
            f"Meyaya Court was removed from <#{previous}>."
            if previous is not None
            else "Meyaya Court was already disabled."
        )
        await ctx.send(
            embed=meyaya_embed(
                "Court Channel Removed",
                description,
                tone="muted",
                icon="⚖️",
            ),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @commands.hybrid_command(
        name="court", description="Take a member to Meyaya Court over a server dispute."
    )
    @app_commands.describe(defendant="Member being accused", reason="Charge or reason for the case")
    @commands.guild_only()
    async def court(
        self,
        ctx: commands.Context,
        defendant: discord.Member,
        *,
        reason: str,
    ) -> None:
        if ctx.guild is None or ctx.channel is None:
            await ctx.send("Court only works inside a server.")
            return
        if defendant.bot:
            await ctx.send("Bots are outside Meyaya's completely fictional jurisdiction.")
            return

        try:
            async with self.bot.db_session() as session:
                service = CourtService(session)
                configured_channel = await service.configured_channel(
                    ctx.guild.id,
                    self.bot.settings.court_channel_id,
                )
                channel_error = court_channel_error(configured_channel, ctx.channel.id)
                if channel_error is not None:
                    await ctx.send(channel_error, ephemeral=ctx.interaction is not None)
                    return
                case = await service.create_case(
                    guild_id=ctx.guild.id,
                    channel_id=ctx.channel.id,
                    plaintiff_id=ctx.author.id,
                    defendant_id=defendant.id,
                    charge=reason,
                )
        except CourtError as exc:
            await ctx.send(str(exc), ephemeral=ctx.interaction is not None)
            return

        view = CourtInvitationView(
            bot=self.bot,
            case_id=case.id,
            defendant_id=defendant.id,
            judge_callback=self._judge_case,
        )
        message = await ctx.send(
            embed=build_court_embed(case),
            view=view,
            allowed_mentions=discord.AllowedMentions(users=True),
        )
        view.message = message

    @staticmethod
    def _can_manage_server(author: discord.abc.User) -> bool:
        permissions = getattr(author, "guild_permissions", None)
        return bool(permissions is not None and permissions.manage_guild)

    async def _judge_case(
        self,
        case_id: int,
        interaction: discord.Interaction,
        message: discord.Message,
        automatic: bool = False,
    ) -> None:
        async with court_case_lock(case_id):
            await self._judge_case_locked(case_id, interaction, message, automatic)

    @discord_context("court")
    async def _judge_case_locked(
        self,
        case_id: int,
        interaction: discord.Interaction,
        message: discord.Message,
        automatic: bool,
    ) -> None:
        try:
            async with self.bot.db_session() as session:
                evidence = await CourtService(session).claim_judging(
                    case_id,
                    interaction.user.id,
                    automatic=automatic,
                )
        except CourtError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        async with self.bot.db_session() as session:
            judging_case = await CourtService(session).get_case(case_id)
        judging_message = message
        try:
            await message.edit(view=None)
            judging_message = await message.channel.send(
                embed=build_court_embed(judging_case),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            decision = await self.judge.judge(evidence)
        except asyncio.CancelledError:
            async with self.bot.db_session() as session:
                await CourtService(session).judging_failed(case_id)
            raise
        except Exception:
            logger.exception("Court judging failed case=%s", case_id)
            decision = None

        if decision is None:
            event("llm_fallback", reason="court_verdict_unavailable", case_id=case_id)
            async with self.bot.db_session() as session:
                case = await CourtService(session).judging_failed(case_id)
            if case.status == CourtStatus.CLARIFYING:
                retry_view: discord.ui.View = CourtClarificationView(
                    bot=self.bot,
                    case_id=case_id,
                    judge_callback=self._judge_case,
                )
            else:
                retry_view = CourtCollectionView(
                    bot=self.bot,
                    case_id=case_id,
                    judge_callback=self._judge_case,
                )
            if case.status == CourtStatus.LOCKED:
                for child in retry_view.children:
                    if getattr(child, "label", "") != "Lock and judge":
                        child.disabled = True
            retry_message = await judging_message.channel.send(
                embed=build_court_embed(case),
                view=retry_view,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            retry_view.message = retry_message
            await interaction.followup.send(
                "Meyaya could not reach a valid verdict. The statements remain saved, so you can retry.",
                ephemeral=True,
            )
            return

        if isinstance(decision, CourtClarification):
            try:
                async with self.bot.db_session() as session:
                    case = await CourtService(session).request_clarification(case_id, decision)
            except CourtError as exc:
                async with self.bot.db_session() as session:
                    await CourtService(session).judging_failed(case_id)
                await interaction.followup.send(str(exc), ephemeral=True)
                return
            clarification_view = CourtClarificationView(
                bot=self.bot,
                case_id=case_id,
                judge_callback=self._judge_case,
            )
            clarification_message = await judging_message.channel.send(
                embed=build_court_embed(case),
                view=clarification_view,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            clarification_view.message = clarification_message
            await interaction.followup.send(
                "Meyaya needs one follow-up answer before delivering a fair verdict.",
                ephemeral=True,
            )
            return

        judgement = decision
        async with self.bot.db_session() as session:
            case = await CourtService(session).complete(case_id, judgement)
        try:
            await judging_message.channel.send(
                embed=self._case_summary_embed(case, judgement),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            await judging_message.channel.send(
                embed=self._verdict_embed(case, judgement),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        finally:
            async with self.bot.db_session() as session:
                await CourtService(session).close(case_id)
        await interaction.followup.send("The verdict has been delivered.", ephemeral=True)

    @staticmethod
    def _case_summary_embed(case: CourtCase, judgement: CourtJudgement) -> discord.Embed:
        embed = meyaya_embed(
            f"Case Summary - #{case.id}",
            f"**Charge:** {case.charge}",
            tone="magic",
            icon="📜",
        )
        embed.add_field(
            name="Plaintiff's statement",
            value=f"<@{case.plaintiff_id}>\n{judgement.plaintiff_summary}",
            inline=False,
        )
        embed.add_field(
            name="Defendant's statement",
            value=f"<@{case.defendant_id}>\n{judgement.defendant_summary}",
            inline=False,
        )
        return embed

    @staticmethod
    def _verdict_embed(case: CourtCase, judgement: CourtJudgement) -> discord.Embed:
        labels = {
            CourtVerdict.GUILTY: ("Guilty", 0xF94144),
            CourtVerdict.NOT_GUILTY: ("Not guilty", 0x57CC99),
            CourtVerdict.MIXED: ("Mixed verdict", 0xF9C74F),
        }
        label, color = labels[judgement.verdict]
        embed = meyaya_embed(
            f"Court Verdict - Case #{case.id}",
            f"## {label}\n**Charge:** {case.charge}",
            color=color,
            icon="⚖️",
        )
        embed.add_field(
            name="Why",
            value=judgement.reasoning,
            inline=False,
        )
        embed.add_field(
            name="What decided the case",
            value=judgement.decisive_factors,
            inline=False,
        )
        if judgement.punishment:
            embed.add_field(
                name="Entertainment-only sentence", value=judgement.punishment, inline=False
            )
        return embed


async def setup(bot: MeyayaBot) -> None:
    await bot.add_cog(CourtCog(bot))
