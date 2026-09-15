"""Fast randomized shipping with a clean reusable avatar card."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import io
import logging
import time

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont, ImageOps

from bot.app import MeyayaBot
from bot.services.ship import ShipService
from bot.utils.embeds import build_ship_embed

logger = logging.getLogger(__name__)

AVATAR_SIZE = 176
AVATAR_FETCH_SIZE = 256
CANVAS_WIDTH = 640
CANVAS_HEIGHT = 260
FILENAME = "ship.png"
CACHE_TTL_SECONDS = 600
MAX_CACHE_ENTRIES = 128


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

    @commands.hybrid_command(
        name="ship",
        description="Roll a fresh compatibility score for two members.",
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
            image_bytes = await self._get_ship_card(user_one, user_two)
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

        image_bytes = await asyncio.to_thread(
            self._render_card,
            avatar_one,
            avatar_two,
            user_one.display_name,
            user_two.display_name,
        )
        self._put_cached(self._card_cache, card_key, image_bytes)
        return image_bytes

    async def _get_avatar_bytes(self, asset: discord.Asset) -> bytes:
        key = str(asset.url)
        cached = self._get_cached(self._avatar_cache, key)
        if cached is not None:
            return cached
        data = await asset.read()
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

    @staticmethod
    def _render_card(
        avatar_one_bytes: bytes,
        avatar_two_bytes: bytes,
        name_one: str,
        name_two: str,
    ) -> bytes:
        canvas = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT))
        draw = ImageDraw.Draw(canvas)
        for y in range(CANVAS_HEIGHT):
            blend = y / max(1, CANVAS_HEIGHT - 1)
            color = (
                int(31 + 28 * blend),
                int(22 + 8 * blend),
                int(45 + 35 * blend),
            )
            draw.line((0, y, CANVAS_WIDTH, y), fill=color)

        draw.rounded_rectangle(
            (18, 8, CANVAS_WIDTH - 18, CANVAS_HEIGHT - 8),
            radius=30,
            fill=(20, 18, 29),
        )
        draw.ellipse((-80, -120, 260, 220), fill=(52, 30, 67))
        draw.ellipse((410, 35, 750, 375), fill=(62, 28, 52))
        draw.rounded_rectangle(
            (18, 8, CANVAS_WIDTH - 18, CANVAS_HEIGHT - 8),
            radius=30,
            outline=(255, 115, 164),
            width=3,
        )

        positions = ((66, 36), (CANVAS_WIDTH - AVATAR_SIZE - 66, 36))
        for avatar_bytes, position in zip(
            (avatar_one_bytes, avatar_two_bytes),
            positions,
            strict=True,
        ):
            avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGB")
            avatar = ImageOps.fit(
                avatar,
                (AVATAR_SIZE, AVATAR_SIZE),
                method=Image.Resampling.LANCZOS,
            )
            mask = Image.new("L", (AVATAR_SIZE, AVATAR_SIZE), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, AVATAR_SIZE - 1, AVATAR_SIZE - 1), fill=255)
            border_box = (
                position[0] - 6,
                position[1] - 6,
                position[0] + AVATAR_SIZE + 6,
                position[1] + AVATAR_SIZE + 6,
            )
            draw.ellipse(border_box, fill=(255, 105, 157))
            canvas.paste(avatar, position, mask)

        center_x = CANVAS_WIDTH // 2
        heart_y = 104
        radius = 25
        draw.ellipse(
            (center_x - 45, heart_y - radius, center_x + 5, heart_y + radius),
            fill=(255, 72, 125),
        )
        draw.ellipse(
            (center_x - 5, heart_y - radius, center_x + 45, heart_y + radius),
            fill=(255, 72, 125),
        )
        draw.polygon(
            (
                (center_x - 45, heart_y + 4),
                (center_x + 45, heart_y + 4),
                (center_x, heart_y + radius * 3),
            ),
            fill=(255, 72, 125),
        )

        name_font = ShipCog._font(24, bold=True)
        ShipCog._draw_centered_name(draw, name_one, positions[0][0], name_font)
        ShipCog._draw_centered_name(draw, name_two, positions[1][0], name_font)

        buffer = io.BytesIO()
        canvas.save(buffer, format="PNG", compress_level=4)
        return buffer.getvalue()

    @staticmethod
    def _font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
        candidates = (
            ("arialbd.ttf", "DejaVuSans-Bold.ttf") if bold else ("arial.ttf", "DejaVuSans.ttf")
        )
        for name in candidates:
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
        return ImageFont.load_default()

    @staticmethod
    def _draw_centered_name(
        draw: ImageDraw.ImageDraw,
        name: str,
        avatar_x: int,
        font: ImageFont.ImageFont,
    ) -> None:
        clean_name = " ".join(name.split())[:30]
        while len(clean_name) > 3:
            candidate_box = draw.textbbox((0, 0), clean_name, font=font)
            if candidate_box[2] - candidate_box[0] <= AVATAR_SIZE + 24:
                break
            clean_name = clean_name[:-2].rstrip() + "…"
        bbox = draw.textbbox((0, 0), clean_name, font=font)
        width = bbox[2] - bbox[0]
        x = avatar_x + AVATAR_SIZE // 2 - width // 2
        y = 222
        draw.text((x + 1, y + 1), clean_name, font=font, fill=(0, 0, 0))
        draw.text((x, y), clean_name, font=font, fill=(255, 235, 244))


async def setup(bot: MeyayaBot) -> None:
    await bot.add_cog(ShipCog(bot))
