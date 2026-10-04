"""Permanent awakenings: database first, bounded visual reveal second."""

import asyncio
import json
import logging
from collections import OrderedDict
from io import BytesIO
from time import monotonic

import discord
from discord.ext import commands

from bot.logging.health import health
from bot.services.fantasy_profile import FantasyProfileService
from bot.services.fantasy_render import render_ritual, render_soul_card, theme_for
from bot.utils.command_context import CommandOutput, remember_command_result
from bot.utils.embeds import meyaya_embed
from bot.utils.image_work import BoundedImageGate, image_work
from bot.views.fantasy import AlreadyAwakenedView, AwakeningView, FantasyProfileView, soul_embed

logger = logging.getLogger(__name__)
MAX_VIEWS = 64


def result_summary(profile, member):
    return dict(
        target_id=profile.user_id,
        target_name=member.display_name[:100],
        class_name=profile.class_name,
        subclass=profile.subclass_name,
        affinity=profile.affinity_name,
        stats=profile.base_stats,
        weapon=profile.weapon_name,
        rarity=profile.weapon_rarity,
        passive=profile.passive_name,
        signature=profile.signature_name,
        title=profile.fantasy_title,
        method="Permanent saved fantasy identity; local random first awakening, not a factual personality assessment.",
    )


class FantasyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.views = set()
        self.pending = {}
        self.render_slots = BoundedImageGate(capacity=3)

    def track_view(self, view):
        if len(self.views) >= MAX_VIEWS:
            view.stop()
            raise commands.CommandError("The Soul Interface is busy. Please try again shortly.")
        self.views.add(view)

    def release_view(self, view):
        self.views.discard(view)
        if self.pending.get(view.owner) is view:
            self.pending.pop(view.owner, None)

    def cog_unload(self):
        for view in tuple(self.views):
            view.finish()

    async def get_profile(self, user_id):
        async with asyncio.timeout(10):
            async with self.bot.db_session() as session:
                return await FantasyProfileService(session).get(user_id)

    async def awaken_user(self, user_id):
        async with asyncio.timeout(10):
            async with self.bot.db_session() as session:
                return await FantasyProfileService(session).awaken(user_id)

    def report(self, error, stage):
        error_id = health.capture(error, command="awaken", stage=stage)
        logger.warning(
            "fantasy_failed stage=%s error_id=%s exception=%s",
            stage,
            error_id,
            type(error).__name__,
        )
        return error_id

    async def card_bytes(self, profile, member):
        async with self.render_slots:
            avatar = b""
            try:
                asset = member.display_avatar.with_size(512).with_format("png")
                avatar = await self.bot.build_profile_aesthetic_service()._download(str(asset))
            except Exception as error:
                # A portrait outage must not stop an already saved identity.
                self.report(error, "fantasy_avatar")
            return await image_work(render_soul_card, profile, member.display_name, avatar)

    async def response(self, profile, member, owner):
        png = None
        try:
            png = await self.card_bytes(profile, member)
        except Exception as error:
            self.report(error, "fantasy_render")
        view = FantasyProfileView(self, owner, profile, member.display_name, image=bool(png))
        self.track_view(view)
        return soul_embed(profile, member.display_name, image=bool(png), bot=self.bot), view, png

    async def reveal(self, interaction, profile):
        theme = theme_for(profile)
        try:
            await interaction.edit_original_response(
                content=None,
                embed=meyaya_embed(
                    "Searching your soul…",
                    "The silence is beginning to answer.",
                    color=int(theme.color[1:], 16),
                    icon="✦",
                ),
                view=None,
            )
            async with self.render_slots:
                gif = await image_work(render_ritual, profile)
            embed = meyaya_embed(
                "Affinity detected",
                f"**{profile.affinity_name}**\nA dormant signature answers.",
                color=int(theme.color[1:], 16),
                icon="✦",
            )
            embed.set_image(url="attachment://meyaya-ritual.gif")
            await interaction.edit_original_response(
                embed=embed, attachments=[discord.File(BytesIO(gif), filename="meyaya-ritual.gif")]
            )
            await asyncio.sleep(2.1)
            await interaction.edit_original_response(
                embed=meyaya_embed(
                    "Your weapon has answered",
                    f"**{profile.weapon_name}**\n{profile.weapon_rarity} · {profile.weapon_type}\n\nYour class is awakening…",
                    color=int(theme.color[1:], 16),
                    icon="✦",
                ),
                attachments=[],
            )
            await asyncio.sleep(0.7)
        except Exception as error:
            self.report(error, "fantasy_reveal")

    async def deliver(self, interaction, profile, member, owner, *, reveal=False, previous=None):
        if reveal:
            await self.reveal(interaction, profile)
        if previous is not None:
            previous.finish()
        embed, view, png = await self.response(profile, member, owner)
        try:
            files = [discord.File(BytesIO(png), filename="meyaya-soul.png")] if png else []
            try:
                message = await interaction.edit_original_response(
                    content=None,
                    embed=embed,
                    view=view,
                    attachments=files,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException:
                view.image = False
                embed = soul_embed(profile, member.display_name, bot=self.bot)
                try:
                    message = await interaction.edit_original_response(
                        content=None,
                        embed=embed,
                        view=view,
                        attachments=[],
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                except discord.HTTPException:
                    message = await interaction.followup.send(
                        embed=embed,
                        view=view,
                        wait=True,
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
            view.message = message
            # Component edits bypass TimedContext.send; retain the actual result
            # so replies to this image-only reveal still have useful context.
            outputs = getattr(self.bot, "_meyaya_command_outputs", None)
            if outputs is None:
                outputs = OrderedDict()
                self.bot._meyaya_command_outputs = outputs
            outputs[(message.channel.id, message.id)] = (
                monotonic(),
                CommandOutput(
                    "awaken",
                    owner,
                    member.display_name[:80],
                    json.dumps(result_summary(profile, member), ensure_ascii=False)[:2000],
                ),
            )
            while len(outputs) > 512:
                outputs.popitem(last=False)
        except BaseException:
            view.finish()
            raise

    @commands.hybrid_command(description="Reveal the permanent fantasy identity hidden within you.")
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def awaken(self, ctx):
        await ctx.defer()
        if ctx.author.id in self.pending:
            await ctx.send(
                "Your awakening door is already open. Use its buttons, or wait for it to close."
            )
            return
        try:
            profile = await self.get_profile(ctx.author.id)
        except Exception as error:
            error_id = self.report(error, "fantasy_lookup")
            await ctx.send(
                f"The Soul Register is unavailable. Please try again later.\nError ID: `{error_id}`"
            )
            return
        if profile is not None:
            view = AlreadyAwakenedView(self, ctx.author.id, profile, ctx.author)
            embed = meyaya_embed(
                "Your soul has already awakened",
                "Your identity is permanent. The same signature follows you across servers.\n\nOpen your Soul Interface below.",
                icon="✦",
            )
        else:
            view = AwakeningView(self, ctx.author.id)
            embed = meyaya_embed(
                "Something within you is stirring…",
                "*A dormant signature waits beyond the veil.*\n\nYour class, affinity, weapon and potential will become a **permanent identity**. This is not a daily draw; there are no rerolls.\n\n**Will you let it answer?**",
                icon="✦",
            )
            embed.set_footer(text="One soul · one awakening · every server")
        self.track_view(view)
        self.pending[ctx.author.id] = view
        try:
            view.message = await ctx.send(
                embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none()
            )
        except BaseException:
            view.finish()
            raise

    @commands.hybrid_command(description="View an awakened fantasy character.")
    @commands.cooldown(1, 8, commands.BucketType.user)
    async def fantasyprofile(self, ctx, member: discord.Member | None = None):
        await ctx.defer()
        member = member or ctx.author
        try:
            profile = await self.get_profile(member.id)
        except Exception as error:
            error_id = self.report(error, "fantasy_lookup")
            await ctx.send(
                f"The Soul Register is unavailable. Please try again later.\nError ID: `{error_id}`"
            )
            return
        if profile is None:
            await ctx.send(
                "Your soul hasn't awakened yet. Use `/awaken` when you're ready."
                if member.id == ctx.author.id
                else "Their soul hasn't awakened yet."
            )
            return
        embed, view, png = await self.response(profile, member, ctx.author.id)
        remember_command_result(ctx, **result_summary(profile, member))
        kwargs = dict(embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none())
        try:
            if png:
                kwargs["file"] = discord.File(BytesIO(png), filename="meyaya-soul.png")
            try:
                view.message = await ctx.send(**kwargs)
            except discord.HTTPException:
                if not png:
                    raise
                kwargs.pop("file", None)
                view.image = False
                kwargs["embed"] = soul_embed(profile, member.display_name, bot=self.bot)
                remember_command_result(ctx, **result_summary(profile, member))
                view.message = await ctx.send(**kwargs)
        except BaseException:
            view.finish()
            raise


async def setup(bot):
    await bot.add_cog(FantasyCog(bot))
