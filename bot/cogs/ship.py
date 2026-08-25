"""Ship command: ships two users, shows a love percentage and a side-by-side profile image."""

from __future__ import annotations

import io
import logging

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageOps, ImageFilter

from bot.app import MeyayaBot
from bot.services.ship import ShipService
from bot.utils.embeds import build_ship_embed

logger = logging.getLogger(__name__)

AVATAR_SIZE = 256  # per-side size (smaller for speed)
GAP = 20
CANVAS_HEIGHT = 320
FILENAME = "ship.png"


class ShipCog(commands.Cog):

    def __init__(self, bot: MeyayaBot) -> None:
        self.bot = bot
        self._text_command: commands.Command | None = None

    async def cog_load(self) -> None:
        self._build_text_command()

    async def cog_unload(self) -> None:
        if self._text_command is not None:
            self.bot.remove_command(self._text_command.name)

    # ---------- slash command ----------

    @app_commands.command(name="ship", description="Ship two users together and see the love percentage")
    @app_commands.describe(user_one="First user", user_two="Second user")
    async def ship(
        self,
        interaction: discord.Interaction,
        user_one: discord.Member,
        user_two: discord.Member,
    ) -> None:
        await interaction.response.defer()
        embed, file = await self._build_ship_response(user_one, user_two)
        await interaction.followup.send(embed=embed, file=file)

    # ---------- text command ----------

    def _build_text_command(self) -> None:
        @commands.command(name="ship")
        async def ship_text(ctx: commands.Context, user_one: discord.Member, user_two: discord.Member) -> None:
            async with ctx.typing():
                embed, file = await self._build_ship_response(user_one, user_two)
            await ctx.send(embed=embed, file=file)

        self.bot.add_command(ship_text)
        self._text_command = ship_text

    # ---------- shared logic ----------

    async def _build_ship_response(
        self,
        user_one: discord.Member,
        user_two: discord.Member,
    ) -> tuple[discord.Embed, discord.File]:
        service = ShipService()
        result = service.ship(user_one.id, user_two.id)
        # Try to fetch a themed GIF quickly (non-blocking if Klipy unavailable)
        gif_url = ""
        klipy = self.bot.build_klipy_service()
        if klipy is not None:
            try:
                query = self._gif_query_for_percentage(result.percentage)
                gif_res = await klipy.random_gif(query, prefer_anime=True)
                gif_url = gif_res.url or ""
            except Exception:
                logger.exception("KLIPY quick fetch failed for ship gif")

        # Check Redis cache for a pre-rendered ship image to keep responses snappy
        image_bytes = None
        redis = getattr(self.bot, "redis", None)
        cache_key = f"ship_img:{result.user_a_id}:{result.user_b_id}:{result.percentage}"
        if redis is not None:
            try:
                cached = await redis.get(cache_key)
                if cached:
                    image_bytes = cached
            except Exception:
                logger.exception("Redis read failed for ship cache")

        if image_bytes is None:
            image_bytes = await self._build_side_by_side_image(user_one, user_two, result)
            if redis is not None:
                try:
                    # cache briefly to speed repeated calls
                    await redis.setex(cache_key, 60, image_bytes)
                except Exception:
                    logger.exception("Redis write failed for ship cache")

        file = discord.File(io.BytesIO(image_bytes), filename=FILENAME)

        embed = build_ship_embed(
            user_a=user_one,
            user_b=user_two,
            percentage=result.percentage,
            label=result.label,
            gif_url=gif_url,
            attachment_filename=FILENAME,
        )
        if gif_url:
            embed.set_thumbnail(url=gif_url)

        return embed, file

    @staticmethod
    def _gif_query_for_percentage(percentage: int) -> str:
        if percentage >= 90:
            return "anime wedding soulmates"
        if percentage >= 70:
            return "anime couple kiss hug"
        if percentage >= 50:
            return "anime blushing love"
        if percentage >= 30:
            return "anime awkward crush"
        return "anime rejected sad friendzone"

    async def _build_side_by_side_image(
        self,
        user_one: discord.Member,
        user_two: discord.Member,
        result: "ShipResult",
    ) -> bytes:
        avatar_bytes = []
        for member in (user_one, user_two):
            asset = member.display_avatar.replace(size=AVATAR_SIZE, format="png")
            avatar_bytes.append(await asset.read())
        # Build circular avatars for a polished look
        avatars = []
        for b in avatar_bytes:
            im = Image.open(io.BytesIO(b)).convert("RGBA")
            im = ImageOps.fit(im, (AVATAR_SIZE, AVATAR_SIZE))
            mask = Image.new("L", (AVATAR_SIZE, AVATAR_SIZE), 0)
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0, AVATAR_SIZE, AVATAR_SIZE), fill=255)
            im.putalpha(mask)
            avatars.append(im)

        canvas_width = AVATAR_SIZE * 2 + GAP
        canvas = Image.new("RGBA", (canvas_width, CANVAS_HEIGHT), (255, 255, 255, 0))

        left_x = 40
        right_x = left_x + AVATAR_SIZE + GAP - 40
        y = 24
        canvas.paste(avatars[0], (left_x, y), avatars[0])
        canvas.paste(avatars[1], (right_x, y), avatars[1])

        draw = ImageDraw.Draw(canvas)

        # Compatibility helper for measuring text across Pillow versions
        def _text_size(text: str, font) -> tuple[int, int]:
            try:
                # Pillow >= 8: textbbox available and accurate
                bbox = draw.textbbox((0, 0), text, font=font)
                return bbox[2] - bbox[0], bbox[3] - bbox[1]
            except Exception:
                try:
                    # Older Pillow: Font.getsize
                    return font.getsize(text)
                except Exception:
                    # Last resort: approximate size
                    return (len(text) * 8, 16)

        # Add soft shadows under avatars for depth
        try:
            shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            sd = ImageDraw.Draw(shadow)
            sd.ellipse((left_x + 8, y + AVATAR_SIZE - 18, left_x + AVATAR_SIZE - 8, y + AVATAR_SIZE + 6), fill=(0, 0, 0, 90))
            sd.ellipse((right_x + 8, y + AVATAR_SIZE - 18, right_x + AVATAR_SIZE - 8, y + AVATAR_SIZE + 6), fill=(0, 0, 0, 90))
            shadow = shadow.filter(ImageFilter.GaussianBlur(8))
            canvas = Image.alpha_composite(shadow, canvas)
            draw = ImageDraw.Draw(canvas)
        except Exception:
            # If ImageFilter not available, ignore shadow
            pass

        # Heart between avatars (stylized)
        heart_x = canvas_width // 2
        heart_y = y + AVATAR_SIZE // 2
        heart_radius = 26
        # outer ring
        draw.ellipse((heart_x - heart_radius - 6, heart_y - heart_radius - 6, heart_x + heart_radius + 6, heart_y + heart_radius + 6), fill=(255, 200, 210, 120))
        # core circle
        draw.ellipse((heart_x - heart_radius, heart_y - heart_radius, heart_x + heart_radius, heart_y + heart_radius), fill=(255, 77, 109, 255))

        # Percentage big text - try to load a nicer font, fallback to default
        try:
            from PIL import ImageFont

            try:
                font_large = ImageFont.truetype("arialbd.ttf", 64)
            except Exception:
                font_large = ImageFont.truetype("arial.ttf", 64)
            font_small = ImageFont.truetype("arial.ttf", 20)
        except Exception:
            from PIL import ImageFont

            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()

        pct_text = f"{result.percentage}%"
        w, h = _text_size(pct_text, font_large)
        # Backdrop for percentage to ensure readability
        pad_x, pad_y = 12, 6
        box_x0 = canvas_width // 2 - w // 2 - pad_x
        box_y0 = 8 - pad_y
        box_x1 = canvas_width // 2 + w // 2 + pad_x
        box_y1 = 8 + h + pad_y
        try:
            draw.rounded_rectangle((box_x0, box_y0, box_x1, box_y1), radius=12, fill=(0, 0, 0, 150))
        except Exception:
            draw.rectangle((box_x0, box_y0, box_x1, box_y1), fill=(0, 0, 0, 150))
        try:
            draw.text((canvas_width // 2 - w // 2, 8), pct_text, font=font_large, fill=(255, 77, 109, 255), stroke_width=2, stroke_fill=(10, 10, 10, 200))
        except Exception:
            draw.text((canvas_width // 2 - w // 2, 8), pct_text, font=font_large, fill=(255, 77, 109, 255))

        # Label beneath percentage
        label_text = result.label
        w2, h2 = _text_size(label_text, font_small)
        draw.text((canvas_width // 2 - w2 // 2, 8 + h + 6), label_text, font=font_small, fill=(120, 120, 120, 255))

        # Small footer with names
        name_y = y + AVATAR_SIZE + 12
        left_name = user_one.display_name
        right_name = user_two.display_name
        fn_w, _ = _text_size(left_name, font_small)
        # Draw a tiny shadow then the name for legibility on dark backgrounds
        shadow_off = 1
        draw.text((left_x + AVATAR_SIZE // 2 - fn_w // 2 + shadow_off, name_y + shadow_off), left_name, font=font_small, fill=(0, 0, 0, 160))
        draw.text((left_x + AVATAR_SIZE // 2 - fn_w // 2, name_y), left_name, font=font_small, fill=(255, 255, 255, 230))
        fn_w2, _ = _text_size(right_name, font=font_small)
        draw.text((right_x + AVATAR_SIZE // 2 - fn_w2 // 2 + shadow_off, name_y + shadow_off), right_name, font=font_small, fill=(0, 0, 0, 160))
        draw.text((right_x + AVATAR_SIZE // 2 - fn_w2 // 2, name_y), right_name, font=font_small, fill=(255, 255, 255, 230))

        buffer = io.BytesIO()
        canvas.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()


async def setup(bot: MeyayaBot) -> None:
    await bot.add_cog(ShipCog(bot))