"""Marriage command: propose, accept/reject, and divorce."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.app import MeyayaBot
from bot.services.marriage import NotMarriedError
from bot.views.marriage import MarriageProposalView

logger = logging.getLogger(__name__)

PROPOSAL_GIF_QUERY = "animation propose ring"


class MarriageCog(commands.Cog):
    def __init__(self, bot: MeyayaBot) -> None:
        self.bot = bot
        self._text_commands: list[commands.Command] = []

    async def cog_load(self) -> None:
        self._build_text_commands()

    async def cog_unload(self) -> None:
        for command in self._text_commands:
            self.bot.remove_command(command.name)

    # ---------- slash commands ----------

    @app_commands.command(name="marry", description="Propose marriage to another user")
    @app_commands.describe(user="The user you want to propose to")
    async def marry(self, interaction: discord.Interaction, user: discord.Member) -> None:
        await interaction.response.defer()

        content, embed, view = await self._build_proposal(interaction.user, user)

        message = await interaction.followup.send(
            content=content,
            embed=embed,
            view=view or discord.utils.MISSING,
            wait=True,
        )

        if view is not None:
            view.message = message

    @app_commands.command(name="divorce", description="End your current marriage")
    async def divorce(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        content = await self._build_divorce(interaction.user.id)
        await interaction.followup.send(content)

    # ---------- text commands ----------

    def _build_text_commands(self) -> None:
        @commands.command(name="marry")
        async def marry_text(ctx: commands.Context, user: discord.Member) -> None:
            content, embed, view = await self._build_proposal(ctx.author, user)

            message = await ctx.send(
                content=content,
                embed=embed,
                view=view or discord.utils.MISSING,
            )

            if view is not None:
                view.message = message

        @commands.command(name="divorce")
        async def divorce_text(ctx: commands.Context) -> None:
            content = await self._build_divorce(ctx.author.id)
            await ctx.send(content)

        self.bot.add_command(marry_text)
        self.bot.add_command(divorce_text)
        self._text_commands = [marry_text, divorce_text]

    # ---------- shared logic ----------

    async def _build_proposal(
        self,
        proposer: discord.abc.User,
        target: discord.abc.User,
    ) -> tuple[str, discord.Embed | None, MarriageProposalView | None]:
        if proposer.id == target.id:
            return (
                "💔 **You can't propose to yourself.** *...or can you?* 😳",
                None,
                None,
            )

        if target.bot:
            return (
                "💔 **That's a bot.** They'll never text back.",
                None,
                None,
            )

        async with self.bot.db_session() as session:
            service = self.bot.build_marriage_service(session)

            if await service.get_active_marriage(proposer.id) is not None:
                return (
                    "💍 **You're already married!** Use `/divorce` first.",
                    None,
                    None,
                )

            if await service.get_active_marriage(target.id) is not None:
                return (
                    f"💔 **{target.display_name} is already married** to someone else.",
                    None,
                    None,
                )

        gif_url = ""
        giphy = self.bot.build_giphy_service()

        if giphy is not None:
            gif_result = await giphy.random_anime_gif(PROPOSAL_GIF_QUERY)
            gif_url = gif_result.url if gif_result else ""

        content = (
            "# 💍 A Marriage Proposal 💍\n\n"
            f"{proposer.mention} **has gotten down on one knee for** {target.mention}**...**\n\n"
            "───────────────────────\n"
            "> *\"Will you marry me?\"* 🥺\n"
            "───────────────────────"
        )

        embed = None

        if gif_url:
            embed = discord.Embed(
                color=discord.Color.from_rgb(255, 182, 193)
            )
            embed.set_image(url=gif_url)

        view = MarriageProposalView(
            self.bot,
            proposer.id,
            target.id,
        )

        return content, embed, view

    async def _build_divorce(self, user_id: int) -> str:
        async with self.bot.db_session() as session:
            service = self.bot.build_marriage_service(session)

            try:
                result = await service.divorce(user_id)
            except NotMarriedError:
                return "💔 **You're not married to anyone right now.**"

        other_id = (
            result.user_b_id
            if result.user_a_id == user_id
            else result.user_a_id
        )

        return (
            "# 💔 Divorce Finalized 💔\n\n"
            f"<@{user_id}> **and** <@{other_id}> **are no longer married.**\n\n"
            "*Sometimes love just doesn't work out...* 😔"
        )


async def setup(bot: MeyayaBot) -> None:
    await bot.add_cog(MarriageCog(bot))