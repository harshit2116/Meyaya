"""Unified member profile command."""

from __future__ import annotations
from sqlalchemy.dialects.postgresql import insert
from bot.models.meyaya_state import MeyayaUserState
from bot.repositories.meyaya_state import MeyayaStateRepository
from bot.services.meyaya_system import MeyayaSystemService

import asyncio
from io import BytesIO

import discord
from discord import app_commands
from discord.ext import commands

from bot.app import MeyayaBot
from bot.services.profile_header import ProfileHeaderRenderer
from bot.services.profilecheck_render import ProfileCheckRenderer
from bot.utils.profile_v2 import sections
from bot.services.profiles import ProfileService
from bot.utils.embeds import build_profile_embed


class ProfileReviewView(discord.ui.LayoutView):
    """Hybrid profile: one cached illustration, fresh native data, lazy review."""

    def __init__(self, bot, target, summary, visual, review_renderer):
        super().__init__(timeout=180)
        self.bot = bot
        self.target = target
        self.review_renderer = review_renderer
        # Retain only compact display data, not downloaded member image bytes.
        self.details = build_profile_embed(target, summary, visual)
        for section in sections(target, summary, visual):
            self.add_item(section)
        review = discord.ui.Button(
            label="Visual review", emoji="✨", style=discord.ButtonStyle.primary
        )
        review.callback = self.visual_review
        details = discord.ui.Button(
            label="More details", emoji="📋", style=discord.ButtonStyle.secondary
        )
        details.callback = self.more_details
        self.add_item(discord.ui.ActionRow(review, details))

    async def visual_review(self, interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        visual = await self.bot.build_profile_aesthetic_service().inspect(self.target)
        _, rendered, extension = await self.review_renderer.render(visual)
        await interaction.followup.send(
            file=discord.File(BytesIO(rendered), filename=f"meyaya-profile-check.{extension}"),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def more_details(self, interaction):
        await interaction.response.send_message(
            embed=self.details, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )


class ProfileCog(commands.Cog):
    """Display Discord, social, marriage, and Meyaya relationship data."""

    def __init__(self, bot: MeyayaBot) -> None:
        self.bot = bot
        self._header_renderer = ProfileHeaderRenderer()
        self._review_renderer = ProfileCheckRenderer()

    @commands.hybrid_command(
        name="nickname", description="View, refresh, keep, or turn off your Meyaya nickname."
    )
    @commands.guild_only()
    @commands.cooldown(1, 15, commands.BucketType.member)
    @app_commands.choices(
        action=[
            app_commands.Choice(name=name.title(), value=name)
            for name in ("status", "refresh", "keep", "reroll", "reject", "on")
        ]
    )
    async def nickname(self, ctx: commands.Context, action: str = "status"):
        action = action.lower().strip()
        if action == "refresh":
            action = "reroll"
        if action not in {"status", "keep", "reroll", "reject", "off", "on"}:
            await ctx.send(
                "Use `nickname status`, `keep`, `reroll`, `reject`, or `on`.", ephemeral=True
            )
            return
        await ctx.defer(ephemeral=True)
        async with self.bot.db_session() as session:
            await session.execute(
                insert(MeyayaUserState)
                .values(guild_id=ctx.guild.id, user_id=ctx.author.id)
                .on_conflict_do_nothing()
            )
            state = await MeyayaStateRepository(session).get_user(
                ctx.guild.id, ctx.author.id, for_update=True
            )
            if action in {"reject", "off"}:
                state.nickname = None
                state.nickname_mode = "off"
                message = "Nickname removed. I won't assign another until you use `nickname on` or `nickname reroll`."
            elif action == "keep":
                if state.nickname:
                    state.nickname_mode = "keep"
                    message = f"Keeping your nickname: {state.nickname}"
                else:
                    message = "You don't have a nickname to keep. Try `nickname reroll`."
            elif action == "reroll":
                previous = state.nickname
                state.nickname = None
                state.nickname_mode = "auto"
                state.nickname_revision += 1
                MeyayaSystemService._assign_nickname_if_ready(
                    state, ctx.author.display_name, force=True, previous=previous
                )
                message = (
                    f"Your new nickname: {state.nickname}"
                    if state.nickname
                    else "I couldn't make a nickname from that display name yet."
                )
            elif action == "on":
                state.nickname_mode = "auto"
                message = "Nicknames are enabled again. I'll assign one as we get to know each other, or use `nickname reroll` now."
            else:
                message = f"Your nickname: {state.nickname or 'None yet'}\nPreference: {state.nickname_mode}"
            await session.commit()
        await ctx.send(
            discord.utils.escape_markdown(message),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @commands.hybrid_command(
        name="profile",
        description="See a member's profile, relationships, activity, and Meyaya bond.",
    )
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
        visual_task = asyncio.create_task(
            self.bot.build_profile_aesthetic_service().inspect(target)
        )
        try:
            async with self.bot.db_session() as session:
                summary = await ProfileService(session).build(target.id, ctx.guild.id)
            visual = await visual_task
        except BaseException:
            visual_task.cancel()
            await asyncio.gather(visual_task, return_exceptions=True)
            raise
        header = await self._header_renderer.render(visual, summary.titles)
        await ctx.send(
            file=discord.File(BytesIO(header), filename="meyaya-profile.png"),
            view=ProfileReviewView(self.bot, target, summary, visual, self._review_renderer),
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: MeyayaBot) -> None:
    await bot.add_cog(ProfileCog(bot))
