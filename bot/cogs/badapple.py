"""Optional full-length Unicode video playback, isolated from other bot services."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, cast

import discord
from discord.ext import commands

from bot.services.badapple import BadApplePlayer, PlaybackBusy
from bot.utils.badapple import MediaError

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from bot.app import MeyayaBot


class BadAppleCog(commands.Cog):
    def __init__(self, bot: MeyayaBot) -> None:
        self.bot = bot
        self.player = BadApplePlayer()

    async def cog_unload(self) -> None:
        await self.player.close()

    # discord.py's decorator typing infers Never for bound cog callbacks in mypy.
    @commands.hybrid_command(  # type: ignore[arg-type]
        name="badapple", description="Play the full Bad Apple!! Unicode animation."
    )
    @commands.guild_only()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def badapple(self, ctx: commands.Context[MeyayaBot]) -> None:
        if ctx.interaction is not None:
            await ctx.defer(ephemeral=True)
        permissions = ctx.channel.permissions_for(cast(discord.Member, ctx.me))
        can_send = (
            permissions.send_messages_in_threads
            if isinstance(ctx.channel, discord.Thread)
            else permissions.send_messages
        )
        if not permissions.view_channel or not can_send:
            await ctx.send(
                "I need View Channel and Send Messages permissions here.", ephemeral=True
            )
            return
        try:
            async with self.player.reserve(ctx.author.id, ctx.channel.id):
                animation = await self.player.load(Path(self.bot.settings.badapple_cache_path))
                fps = min(self.bot.settings.badapple_fps, animation.fps)
                await ctx.send(
                    f"Starting {len(animation.frames)} frames, source {animation.duration:.1f}s, "
                    f"target {fps:g} FPS (at least {len(animation.frames) / fps:.0f}s). "
                    "Use 'uwu badapplestop' here to cancel.",
                    ephemeral=True,
                )
                # A channel Message uses bot authentication and plain content. Context
                # responses become V2 cards; interaction webhooks expire after 15 min.
                message = await ctx.channel.send(
                    "Bad Apple!! — preparing the first frame…",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                result = await self.player.play(message, animation, fps)
                logger.info(
                    "badapple_complete frames=%s seconds=%.1f target_fps=%.2f actual_fps=%.2f",
                    result.frames,
                    result.seconds,
                    result.target_fps,
                    result.actual_fps,
                )
        except PlaybackBusy:
            await ctx.send(
                "A Bad Apple animation is already running. Try again after it ends.", ephemeral=True
            )
        except MediaError:
            logger.warning("badapple_media_unavailable", exc_info=True)
            await ctx.send(
                "Bad Apple media is unavailable or invalid.",
                ephemeral=True,
            )
        except (discord.HTTPException, discord.RateLimited, TimeoutError) as exc:
            # Do not immediately hit the failed edit route again, especially on 429.
            logger.warning(
                "badapple_discord_stopped error=%s status=%s",
                type(exc).__name__,
                getattr(exc, "status", None),
            )
            if ctx.interaction is None or not ctx.interaction.is_expired():
                try:
                    await ctx.send(
                        "Bad Apple stopped because Discord could not accept an update. "
                        "The animation slot has been released.",
                        ephemeral=True,
                    )
                except (discord.HTTPException, discord.RateLimited):
                    pass

    @commands.hybrid_command(  # type: ignore[arg-type]
        name="badapplestop",
        description="Stop your Bad Apple animation or moderate one in this channel.",
    )
    @commands.guild_only()
    async def badapplestop(self, ctx: commands.Context[MeyayaBot]) -> None:
        if ctx.interaction is not None:
            await ctx.defer(ephemeral=True)
        if self.player.task is None or self.player.channel_id != ctx.channel.id:
            await ctx.send("No Bad Apple animation is running in this channel.", ephemeral=True)
            return
        if (
            ctx.author.id != self.player.owner_id
            and not ctx.channel.permissions_for(cast(discord.Member, ctx.author)).manage_messages
        ):
            await ctx.send(
                "Only the starter or a member with Manage Messages can stop this animation.",
                ephemeral=True,
            )
            return
        await self.player.stop()
        await ctx.send("Bad Apple playback cancelled.", ephemeral=True)


async def setup(bot: MeyayaBot) -> None:
    await bot.add_cog(BadAppleCog(bot))
