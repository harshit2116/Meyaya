"""Fast randomized shipping with a clean reusable avatar card."""

from __future__ import annotations

import asyncio
from bot.utils.image_work import image_work
from dataclasses import dataclass
import io
import logging
import time

import discord
from discord import app_commands
from discord.ext import commands


from bot.app import MeyayaBot
from bot.services.ship import ShipService
from bot.services.ship_card import render_ship_card
from bot.utils.embeds import build_ship_embed

logger = logging.getLogger(__name__)


AVATAR_FETCH_SIZE = 256


FILENAME = "ship.png"
CACHE_TTL_SECONDS = 600
MAX_CACHE_ENTRIES = 16


@dataclass(frozen=True, slots=True)
class ByteCacheEntry:
    data: bytes
    expires_at: float


class ShipCog(commands.Cog):
    """Ship two members with a new score on every invocation."""

    def __init__(self, bot: MeyayaBot) -> None:
        self.bot = bot
        self.service = ShipService()
        self._avatar_cache: dict[object, ByteCacheEntry] = {}
        self._card_cache: dict[object, ByteCacheEntry] = {}
        self._avatar_locks = [asyncio.Lock() for _ in range(16)]

    @commands.hybrid_command(
        name="ship",
        description="Measure the romantic chemistry between two members.",
    )
    @app_commands.describe(user_one="First member", user_two="Second member")
    async def ship(
        self,
        ctx: commands.Context,
        user_one: discord.Member,
        user_two: discord.Member,
    ) -> None:
        if ctx.interaction is not None:
            await ctx.defer()
            embed, file = await self._build_ship_response(user_one, user_two)
        else:
            async with ctx.typing():
                embed, file = await self._build_ship_response(user_one, user_two)
        if file is None:
            await ctx.send(embed=embed)
        else:
            await ctx.send(embed=embed, file=file)

    async def _build_ship_response(
        self,
        user_one: discord.Member,
        user_two: discord.Member,
    ) -> tuple[discord.Embed, discord.File | None]:
        result = self.service.ship(user_one.id, user_two.id)
        image_bytes: bytes | None = None
        try:
            image_bytes = await self._get_ship_card(
                user_one, user_two, result.percentage, result.label
            )
        except Exception:
            logger.exception(
                "Failed to render ship card users=%s,%s",
                user_one.id,
                user_two.id,
            )

        file = (
            discord.File(io.BytesIO(image_bytes), filename=FILENAME)
            if image_bytes is not None
            else None
        )
        embed = build_ship_embed(
            user_a=user_one,
            user_b=user_two,
            percentage=result.percentage,
            label=result.label,
            attachment_filename=FILENAME if file is not None else None,
        )
        return embed, file

    async def _get_ship_card(
        self,
        user_one: discord.Member,
        user_two: discord.Member,
        percentage: int,
        label: str,
        *,
        theme: str = "ship",
    ) -> bytes:
        asset_one = user_one.display_avatar.replace(
            size=AVATAR_FETCH_SIZE,
            format="png",
        )
        asset_two = user_two.display_avatar.replace(
            size=AVATAR_FETCH_SIZE,
            format="png",
        )
        card_key = (
            theme,
            percentage,
            label,
            str(asset_one.url),
            str(asset_two.url),
            user_one.display_name,
            user_two.display_name,
        )
        cached = self._get_cached(self._card_cache, card_key)
        if cached is not None:
            return cached

        if asset_one.url == asset_two.url:
            avatar_one = await self._get_avatar_bytes(asset_one)
            avatar_two = avatar_one
        else:
            avatar_one, avatar_two = await asyncio.gather(
                self._get_avatar_bytes(asset_one),
                self._get_avatar_bytes(asset_two),
            )

        image_bytes = await image_work(
            render_ship_card,
            avatar_one,
            avatar_two,
            user_one.display_name,
            user_two.display_name,
            percentage,
            label,
            theme=theme,
        )
        self._put_cached(self._card_cache, card_key, image_bytes)
        return image_bytes

    async def _get_avatar_bytes(self, asset: discord.Asset) -> bytes:
        key = str(asset.url)
        async with self._avatar_locks[hash(key) % len(self._avatar_locks)]:
            return await self._download_avatar(asset, key)

    async def _download_avatar(self, asset, key) -> bytes:
        cached = self._get_cached(self._avatar_cache, key)
        if cached is not None:
            return cached
        data = await asyncio.wait_for(asset.read(), timeout=5)
        self._put_cached(self._avatar_cache, key, data)
        return data

    @staticmethod
    def _get_cached(
        cache: dict[object, ByteCacheEntry],
        key: object,
    ) -> bytes | None:
        entry = cache.get(key)
        if entry is None:
            return None
        if entry.expires_at <= time.monotonic():
            cache.pop(key, None)
            return None
        return entry.data

    @staticmethod
    def _put_cached(
        cache: dict[object, ByteCacheEntry],
        key: object,
        data: bytes,
    ) -> None:
        now = time.monotonic()
        if len(cache) >= MAX_CACHE_ENTRIES and key not in cache:
            expired_keys = [
                cache_key for cache_key, entry in cache.items() if entry.expires_at <= now
            ]
            for expired_key in expired_keys:
                cache.pop(expired_key, None)
            if len(cache) >= MAX_CACHE_ENTRIES:
                cache.pop(next(iter(cache)))
        cache[key] = ByteCacheEntry(data=data, expires_at=now + CACHE_TTL_SECONDS)
        while sum(len(entry.data) for entry in cache.values()) > 4 * 1024 * 1024:
            cache.pop(next(iter(cache)))

    _render_card = staticmethod(render_ship_card)


async def setup(bot: MeyayaBot) -> None:
    await bot.add_cog(ShipCog(bot))
