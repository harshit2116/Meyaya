"""Quick-start guide and community support commands."""

import asyncio
import logging

import discord
from discord.ext import commands
from sqlalchemy.exc import SQLAlchemyError

from bot.utils.components_v2 import MeyayaView
from bot.utils.embeds import meyaya_embed
from bot.views.first_use import FirstUseView, first_use_embed

LOUNGE_URL = "https://discord.gg/e9bK5ZbUZS"
logger = logging.getLogger(__name__)


class ExtrasCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(
        name="guide", description="See a short guide to chatting and playing with Meyaya."
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def guide(self, ctx):
        guild_id = ctx.guild.id if ctx.guild else None
        view = FirstUseView(self.bot, ctx.author.id)
        view.message = await ctx.send(
            embed=first_use_embed(self.bot, guild_id),
            view=view,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        service = getattr(self.bot, "first_use", None)
        if service is not None:
            try:
                async with asyncio.timeout(5):
                    claim = await service.claim(ctx.author.id)
                    if claim.state == "new":
                        await service.finish(ctx.author.id, claim.token)
            except (SQLAlchemyError, TimeoutError):
                logger.warning("Manual guide acknowledgement unavailable")

    @commands.hybrid_command(name="feedback", description="Report a bug or suggest a feature in Pondside Lounge.")
    async def feedback(self, ctx):
        view = MeyayaView()
        view.add_item(discord.ui.Button(label="Join Pondside Lounge", url=LOUNGE_URL))
        await ctx.send(embed=meyaya_embed("Pondside Lounge", "Found a bug or have an idea? Join us to report an issue, suggest a feature, or try Meyaya without the server chat limit.", icon="🌸"), view=view)


async def setup(bot):
    await bot.add_cog(ExtrasCog(bot))
