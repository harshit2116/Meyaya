"""Quick-start guide and community support commands."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, cast

import discord
from discord.ext import commands
from sqlalchemy.exc import SQLAlchemyError

from bot.utils.components_v2 import MeyayaView
from bot.utils.embeds import meyaya_embed
from bot.views.first_use import FirstUseView, first_use_embed

if TYPE_CHECKING:
    from bot.app import MeyayaBot

LOUNGE_URL = "https://discord.gg/e9bK5ZbUZS"
logger = logging.getLogger(__name__)


class ExtrasCog(commands.Cog):
    def __init__(self, bot: MeyayaBot) -> None:
        self.bot = bot

    @commands.hybrid_command(  # type: ignore[arg-type]
        name="guide", description="See a short guide to chatting and playing with Meyaya."
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def guide(self, ctx: commands.Context[Any]) -> None:
        guild_id = ctx.guild.id if ctx.guild else None
        view = cast(Any, FirstUseView)(self.bot, ctx.author.id, guild_id=guild_id)
        view.message = await ctx.send(
            embed=cast(Any, first_use_embed)(self.bot, guild_id),
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

    @commands.hybrid_command(  # type: ignore[arg-type]
        name="feedback", description="Report a bug or suggest a feature in Pondside Lounge."
    )
    async def feedback(self, ctx: commands.Context[Any]) -> None:
        view = MeyayaView()
        view.add_item(discord.ui.Button(label="Join Pondside Lounge", url=LOUNGE_URL))
        await ctx.send(
            embed=meyaya_embed(
                "Pondside Lounge",
                "Found a bug or have an idea? Join us to report an issue, suggest a feature, or try Meyaya without the server chat limit.",
                icon="🌸",
            ),
            view=view,
        )


async def setup(bot: MeyayaBot) -> None:
    await bot.add_cog(ExtrasCog(bot))
