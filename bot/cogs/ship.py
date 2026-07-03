"""Ship command: ships two users, shows a love percentage and a side-by-side profile image."""

from __future__ import annotations

import io
import logging

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageOps

from bot.app import MeyayaBot
from bot.services.ship import ShipService
from bot.utils.embeds import build_ship_embed

logger = logging.getLogger(__name__)

AVATAR_SIZE = 512  # big, per side
GAP = 24
CANVAS_HEIGHT = AVATAR_SIZE
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

        gif_result = None
        giphy = self.bot.build_giphy_service()
        if giphy is not None:
            query = self._gif_query_for_percentage(result.percentage)
            gif_result = await giphy.random_anime_gif(query)
        gif_url = gif_result.url if gif_result else ""

        image_bytes = await self._build_side_by_side_image(user_one, user_two)
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
    ) -> bytes:
        avatar_bytes = []
        for member in (user_one, user_two):
            asset = member.display_avatar.replace(size=AVATAR_SIZE, format="png")
            avatar_bytes.append(await asset.read())

        avatars = [ImageOps.fit(Image.open(io.BytesIO(b)).convert("RGBA"), (AVATAR_SIZE, AVATAR_SIZE)) for b in avatar_bytes]

        canvas_width = AVATAR_SIZE * 2 + GAP
        canvas = Image.new("RGBA", (canvas_width, CANVAS_HEIGHT), (0, 0, 0, 0))

        canvas.paste(avatars[0], (0, 0))
        canvas.paste(avatars[1], (AVATAR_SIZE + GAP, 0))
        # Heart divider in the gap.
        heart_draw = ImageDraw.Draw(canvas)
        cx = AVATAR_SIZE + GAP // 2
        cy = CANVAS_HEIGHT // 2
        heart_draw.ellipse((cx - GAP // 2, cy - GAP // 2, cx + GAP // 2, cy + GAP // 2), fill=(255, 77, 109, 255))

        buffer = io.BytesIO()
        canvas.save(buffer, format="PNG")
        return buffer.getvalue()


async def setup(bot: MeyayaBot) -> None:
    await bot.add_cog(ShipCog(bot))