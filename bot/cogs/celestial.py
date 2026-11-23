"""System-driven fortune and fantasy commands with shared image output."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from io import BytesIO
from time import monotonic
from typing import TYPE_CHECKING, Any, cast

import discord
from discord.ext import commands

from bot.services.celestial import draw_card, render_card
from bot.utils.command_context import remember_command_result
from bot.utils.image_work import BoundedImageGate, image_work

if TYPE_CHECKING:
    from bot.app import MeyayaBot


class CelestialCog(commands.Cog):
    def __init__(self, bot: MeyayaBot) -> None:
        self.bot = bot
        self.cache: OrderedDict[tuple[Any, str, str], bytes] = OrderedDict()
        self.render_slots = BoundedImageGate(concurrency=2)
        self.avatar_cache: OrderedDict[str, tuple[float, bytes]] = OrderedDict()

    async def show(
        self,
        ctx: commands.Context[Any],
        kind: str,
        member: discord.Member | None = None,
        question: str = "",
    ) -> None:
        target: discord.Member | discord.User = member or ctx.author
        await ctx.defer()
        result = cast(Any, draw_card)(
            kind, ctx.guild.id if ctx.guild else 0, target.id, question=question[:300]
        )
        key = (result, target.display_name, str(target.display_avatar.url))
        png = await self._card_bytes(key, result, target)
        lines = [f"**{discord.utils.escape_markdown(target.display_name)} - {result.title}**"]
        lines.extend(f"**{k}:** {v}" for k, v in result.fields)
        lines.extend(f"**{p}: {title}** - {meaning}" for p, title, meaning in result.panels)
        cast(Any, remember_command_result)(
            ctx,
            target_id=target.id,
            target_name=target.display_name,
            title=result.title,
            day=result.day,
            fields=dict(result.fields),
            panels=result.panels,
            question=question[:300],
            method="Deterministic daily fantasy draw for entertainment; not a factual prediction.",
        )
        await ctx.send(
            None if kind in {"fortune", "tarot", "fate", "guardian"} else "\n".join(lines),
            file=discord.File(BytesIO(png), filename=f"{kind}.png"),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def _card_bytes(
        self,
        key: tuple[Any, str, str],
        result: Any,
        member: discord.abc.User,
    ) -> bytes:
        # A ready card needs neither a download nor the render queue.
        png = self.cache.get(key)
        if png is not None:
            self.cache.move_to_end(key)
            return png
        async with self.render_slots:
            png = self.cache.get(key)
            if png is None:
                size = 512 if getattr(result, "kind", None) == "fortune" else 128
                asset = member.display_avatar.with_size(size).with_format("png")
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
                        while (
                            len(self.avatar_cache) > 32
                            or sum(len(v[1]) for v in self.avatar_cache.values()) > 1024 * 1024
                        ):
                            self.avatar_cache.popitem(last=False)
                png = cast(
                    bytes,
                    await cast(Any, image_work)(render_card, result, member.display_name, avatar),
                )
                # Retry a failed avatar fetch next time instead of retaining
                # a missing portrait for the rest of this daily draw.
                if avatar:
                    self.cache[key] = png
                    while (
                        len(self.cache) > 8
                        or sum(map(len, self.cache.values())) > 4 * 1024 * 1024
                    ):
                        self.cache.popitem(last=False)
            else:
                self.cache.move_to_end(key)
        return png

    @commands.hybrid_command(  # type: ignore[arg-type]
        description="Reveal today's fortune and ask an optional question."
    )
    @commands.cooldown(1, 5, commands.BucketType.member)
    async def fortune(
        self,
        ctx: commands.Context[Any],
        member: discord.Member | None = None,
        *,
        question: str = "",
    ) -> None:
        await self.show(ctx, "fortune", member, question)


def make_command(name: str) -> commands.HybridCommand[Any, ..., Any]:
    async def callback(
        self: CelestialCog,
        ctx: commands.Context[Any],
        member: discord.Member | None = None,
    ) -> None:
        await self.show(ctx, name, member)

    callback.__name__ = name
    callback.__qualname__ = f"CelestialCommands.{name}"
    callback = commands.cooldown(1, 5, commands.BucketType.member)(callback)
    return commands.hybrid_command(
        name=name, description=f"Reveal your daily {name} card."
    )(callback)


CelestialCommands: type[CelestialCog] = type(
    "CelestialCommands",
    (CelestialCog,),
    {name: make_command(name) for name in ("tarot", "fate")},
)


async def setup(bot: MeyayaBot) -> None:
    await bot.add_cog(CelestialCommands(bot))
