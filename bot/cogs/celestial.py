"""System-driven fortune and fantasy commands with shared image output."""

from __future__ import annotations
import asyncio
from time import monotonic
from bot.utils.image_work import image_work, BoundedImageGate
from io import BytesIO
from collections import OrderedDict
import discord
from discord.ext import commands
from bot.services.celestial import draw_card, render_card


class CelestialCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cache = OrderedDict()
        self.render_slots = BoundedImageGate()
        self.avatar_cache = OrderedDict()

    async def show(self, ctx, kind, member=None, question=""):
        member = member or ctx.author
        await ctx.defer()
        result = draw_card(
            kind, ctx.guild.id if ctx.guild else 0, member.id, question=question[:300]
        )
        key = (result, member.display_name, str(member.display_avatar.url))
        async with self.render_slots:
            png = self.cache.get(key)
            if png is None:
                asset = member.display_avatar.with_size(128).with_format("png")
                avatar_key = str(asset)
                cached = self.avatar_cache.get(avatar_key)
                if cached and monotonic() - cached[0] < 600:
                    avatar = cached[1]
                    self.avatar_cache.move_to_end(avatar_key)
                else:
                    try:
                        avatar = await asyncio.wait_for(asset.read(), timeout=5)
                    except (discord.HTTPException, TimeoutError):
                        avatar = b""
                    if avatar:
                        self.avatar_cache[avatar_key] = (monotonic(), avatar)
                        while len(self.avatar_cache) > 32 or sum(len(v[1]) for v in self.avatar_cache.values()) > 1024 * 1024:
                            self.avatar_cache.popitem(last=False)
                png = await image_work(render_card, result, member.display_name, avatar)
                self.cache[key] = png
                while len(self.cache) > 8 or sum(map(len, self.cache.values())) > 4 * 1024 * 1024:
                    self.cache.popitem(last=False)
            else:
                self.cache.move_to_end(key)
        lines = [f"**{discord.utils.escape_markdown(member.display_name)} - {result.title}**"]
        lines.extend(f"**{k}:** {v}" for k, v in result.fields)
        lines.extend(f"**{p}: {title}** - {meaning}" for p, title, meaning in result.panels)
        if kind == "guardian":
            from bot.services.card_renderer import GUARDIANS

            icon = GUARDIANS.get(result.title, "owl")

        await ctx.send(
            None if kind in {"fortune", "fate"} else "\n".join(lines),
            file=discord.File(BytesIO(png), filename=f"{kind}.png"),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @commands.hybrid_command(description="Reveal today's fortune and ask an optional question.")
    @commands.cooldown(1, 5, commands.BucketType.member)
    async def fortune(self, ctx, member: discord.Member | None = None, *, question: str = ""):
        await self.show(ctx, "fortune", member, question)


def make_command(name):
    async def callback(self, ctx: commands.Context, member: discord.Member = None):
        await self.show(ctx, name, member)

    callback.__name__ = name
    callback.__qualname__ = f"CelestialCommands.{name}"
    callback = commands.cooldown(1, 5, commands.BucketType.member)(callback)
    return commands.hybrid_command(name=name, description=f"Reveal your daily {name} card.")(
        callback
    )


CelestialCommands = type(
    "CelestialCommands",
    (CelestialCog,),
    {name: make_command(name) for name in ("tarot", "fate", "guardian")},
)


async def setup(bot):
    await bot.add_cog(CelestialCommands(bot))
