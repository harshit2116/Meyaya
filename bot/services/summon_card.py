"""Local illustrated AniList summon cards with bounded, transient caches."""

import asyncio
from collections import OrderedDict
from functools import lru_cache
from io import BytesIO
import math
from pathlib import Path
from time import monotonic
from urllib.parse import urlparse

import aiohttp
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

from bot.services.aura_archive import _asset, _serif, _spark, _text
from bot.services.character_catalog import RARITY_NAMES
from bot.services.character_provider import safe_anilist_image
from bot.utils.image_work import BoundedImageGate, image_work

SIZE = (1500, 1000)
RARITY_COLORS = {2: "#b6c2d5", 3: "#b8a5ff", 4: "#cf99ef", 5: "#f4d08f", 6: "#ff91c5"}
IMAGE_LIMIT = 4 * 1024 * 1024


@lru_cache(maxsize=1)
def _frame():
    path = Path(__file__).resolve().parents[1] / "assets/celestial/summon/card-frame.png"
    with Image.open(path) as art:
        source = art.convert("RGBA").resize(SIZE, Image.Resampling.LANCZOS)
    result = ImageOps.colorize(
        ImageOps.grayscale(source), "#21182e", "#ffd9ed", mid="#b174a3", midpoint=170
    ).convert("RGBA")
    # Artwork is decorative, never a text backdrop. Fade it out before the
    # right-hand reading column, including long passives and the rights notice.
    clear = Image.new("L", SIZE)
    ImageDraw.Draw(clear).rectangle((695, 130, 1410, 963), fill=255)
    clear = clear.filter(ImageFilter.GaussianBlur(12))
    result.putalpha(ImageChops.multiply(source.getchannel("A"), ImageChops.invert(clear)))
    return result


@lru_cache(maxsize=1)
def _portrait_mask():
    mask = Image.new("L", (580, 880))
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, 579, 579), fill=255)
    draw.rounded_rectangle((0, 285, 579, 879), radius=65, fill=255)
    return mask


@lru_cache(maxsize=24)
def _native_font(size):
    for path in (
        "C:/Windows/Fonts/YuGothM.ttc",
        "C:/Windows/Fonts/meiryo.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ):
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return None


@lru_cache(maxsize=16)
def _signature_font(size):
    for path in (
        "C:/Windows/Fonts/segoesc.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
    ):
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return _serif(size)


def _star(draw, x, y, r, color):
    points = []
    for index in range(10):
        a = index * math.pi / 5 - math.pi / 2
        radius = r if index % 2 == 0 else r * 0.43
        points.append((x + math.cos(a) * radius, y + math.sin(a) * radius))
    draw.polygon(points, fill=color)


def _seal(draw, x, y, color, kind):
    draw.ellipse((x - 41, y - 41, x + 41, y + 41), fill="#191528", outline=color, width=2)
    if kind == "class":
        draw.arc((x - 23, y - 25, x + 24, y + 25), 65, 300, fill=color, width=8)
        _spark(draw, x + 8, y, 14, color)
        _spark(draw, x + 20, y - 20, 6, color)
    elif kind == "traits":
        for i in range(5):
            angle = i * math.tau / 5
            cx, cy = x + math.sin(angle) * 13, y + math.cos(angle) * 13
            draw.ellipse((cx - 8, cy - 13, cx + 8, cy + 13), fill=color)
    else:
        draw.rounded_rectangle((x - 22, y - 19, x - 1, y + 22), radius=4, fill=color)
        draw.rounded_rectangle((x + 1, y - 13, x + 23, y + 27), radius=4, outline=color, width=3)
        _spark(draw, x - 11, y + 1, 6, "#352039")


def render_summon_card(gameplay, display, portrait=None, avatar=None, member_name=""):
    """Use provider artwork as supplied; rarity and gameplay are never rerolled."""
    accent = RARITY_COLORS[gameplay.rarity_stars]
    image = Image.new("RGBA", SIZE, "#0e1020")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((24, 24, 1476, 976), radius=32, fill="#101120", outline=accent, width=1)
    art = _asset(portrait) if not gameplay.image_disabled else None
    if art is None:
        art = Image.new("RGBA", (580, 880), "#211c32")
        placeholder = ImageDraw.Draw(art)
        _spark(placeholder, 290, 350, 65, accent)
        message = "ARTWORK HIDDEN" if gameplay.image_disabled else "ARTWORK UNAVAILABLE"
        _text(placeholder, (65, 470, 450, 80), message, 26, "#d9c1df", minimum=18)
    image.paste(ImageOps.fit(art, (580, 880), Image.Resampling.LANCZOS), (62, 48), _portrait_mask())
    # Darken only the signature area, keeping the supplied character art intact.
    shade = Image.new("RGBA", (580, 880))
    sd = ImageDraw.Draw(shade)
    for y in range(680, 880):
        sd.line((0, y, 579, y), fill=(14, 10, 24, round((y - 680) / 200 * 180)))
    image.alpha_composite(shade, (62, 48))
    draw = ImageDraw.Draw(image)
    draw.rectangle((680, 26, 1474, 974), fill="#101120")
    draw.rounded_rectangle((694, 544, 1472, 687), radius=20, fill="#281a31")
    draw.rounded_rectangle((694, 706, 1470, 808), radius=18, fill="#181529")
    image.alpha_composite(_frame())
    draw = ImageDraw.Draw(image)
    draw.text((754, 57), "M E Y A Y A  S U M M O N", font=_serif(22), fill="#d6a3db")
    _spark(draw, 716, 70, 14, "#f5adce")
    draw.rounded_rectangle((1184, 43, 1398, 93), radius=25, fill="#211f40", outline=accent, width=2)
    draw.text(
        (1205, 54), RARITY_NAMES[gameplay.rarity_stars].upper(), font=_serif(23), fill="#f6e9ff"
    )
    # All six supported tiers fit without substituting a textual star glyph.
    for index in range(gameplay.rarity_stars):
        _star(draw, 1210 + index * 30, 110, 7, accent)
    draw.line((700, 125, 1448, 125), fill="#524368")
    _text(draw, (710, 141, 590, 83), display.name, 55, "#f4eeff", minimum=25)
    native_font = _native_font(23)
    if display.native_name and native_font is not None:
        native = display.native_name[:24]
        draw.text((713, 236), native, font=native_font, fill="#d7b7ee")
        # Vertical name strip follows the reference and remains optional when
        # a production host has no CJK font installed.
        draw.rounded_rectangle((76, 265, 121, 555), radius=12, fill="#241a32")
        for index, char in enumerate(display.native_name[:8]):
            draw.text((87, 281 + index * 30), char, font=native_font, fill="#f1c4e6")
    _text(draw, (713, 281, 660, 57), display.series, 29, "#dfd3f1", minimum=18)
    member_art = _asset(avatar)
    if member_art is not None:
        member_art = ImageOps.fit(member_art, (128, 128), Image.Resampling.LANCZOS)
        mask = Image.new("L", (128, 128))
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, 127, 127), radius=18, fill=255)
        image.paste(member_art, (1322, 148), mask)
    draw = ImageDraw.Draw(image)
    draw.line((700, 344, 1447, 344), fill="#514566")
    _seal(draw, 749, 401, accent, "class")
    draw.text((820, 373), "C L A S S", font=_serif(17), fill=accent)
    _text(draw, (820, 402, 555, 58), gameplay.class_name, 34, "#f3e8fc", minimum=22)
    draw.line((820, 454, 1445, 454), fill="#514566")
    _seal(draw, 749, 497, "#e69cc9", "traits")
    draw.text((820, 464), "T R A I T S", font=_serif(17), fill="#e6b4de")
    _text(
        draw,
        (820, 489, 555, 47),
        " · ".join(gameplay.traits) or "Mysterious",
        29,
        "#edc4e4",
        minimum=17,
    )
    _seal(draw, 749, 619, "#f286b4", "passive")
    draw.text((827, 568), "S I G N A T U R E  P A S S I V E", font=_serif(18), fill="#ff92c1")
    _text(
        draw,
        (827, 605, 535, 74),
        gameplay.passive or "Unknown potential",
        29,
        "#f4c7e3",
        minimum=18,
    )
    draw.line((1076, 712, 1076, 777), fill="#9b6d9e")
    _spark(draw, 739, 743, 14, "#d68cc7")
    draw.text((789, 717), "R O S T E R  I D", font=_serif(16), fill=accent)
    draw.text((789, 748), f"#{gameplay.internal_id:04d}", font=_serif(27), fill="#f4e8fa")
    _spark(draw, 1124, 743, 14, accent)
    draw.text((1178, 717), "P R O V I D E R", font=_serif(16), fill=accent)
    draw.text((1178, 748), "AniList", font=_serif(27), fill="#f4e8fa")
    # These are card text, not painted imitation buttons: the live action is
    # a native Discord button delivered under the image.
    draw.line((706, 823, 1449, 823), fill="#715475")
    _text(draw, (711, 845, 660, 42), "Summoned for " + member_name, 28, "#edc2df", minimum=18)
    _text(
        draw,
        (711, 914, 660, 44),
        "Character data and artwork: AniList. Rights belong to their respective owners.",
        17,
        "#b9a4cd",
        minimum=14,
    )
    signature = " ".join(display.name.split())[:60]
    signature_font = _signature_font(43)
    while signature_font.size > 22 and draw.textlength(signature, font=signature_font) > 464:
        signature_font = _signature_font(signature_font.size - 1)
    draw.text(
        (125, 830),
        signature,
        font=signature_font,
        fill="#ffc4df",
        stroke_width=1,
        stroke_fill="#322034",
    )
    output = BytesIO()
    image.convert("RGB").save(output, "PNG", compress_level=3)
    return output.getvalue()


class SummonCardRenderer:
    """Memory-only TTL caches, safe bounded HTTP reads and off-loop rendering."""

    def __init__(self, session):
        self.session = session
        self.assets = OrderedDict()
        self.cards = OrderedDict()
        self.asset_bytes = 0
        self.card_bytes = 0
        self.gate = BoundedImageGate()

    @staticmethod
    def _prune(cache, now):
        removed = 0
        for key, (expires, data) in list(cache.items()):
            if expires <= now:
                del cache[key]
                removed += len(data)
        return removed

    async def _download(self, url, *, character=False):
        if not url or self.session is None:
            return None
        parsed = urlparse(url)
        safe = (
            safe_anilist_image(url)
            if character
            else (
                parsed.scheme == "https"
                and parsed.hostname in {"cdn.discordapp.com", "media.discordapp.net"}
                and not parsed.username
                and not parsed.password
            )
        )
        if not safe:
            return None
        self.asset_bytes -= self._prune(self.assets, monotonic())
        if url in self.assets:
            self.assets.move_to_end(url)
            return self.assets[url][1]
        try:
            async with self.session.get(
                url, timeout=aiohttp.ClientTimeout(total=8), allow_redirects=False
            ) as response:
                if response.status != 200 or (response.content_length or 0) > IMAGE_LIMIT:
                    return None
                data = bytearray()
                async for chunk in response.content.iter_chunked(64 * 1024):
                    data.extend(chunk)
                    if len(data) > IMAGE_LIMIT:
                        return None
                data = bytes(data)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return None
        while self.assets and (
            self.asset_bytes + len(data) > 8 * 1024 * 1024 or len(self.assets) >= 32
        ):
            _, (_, removed) = self.assets.popitem(last=False)
            self.asset_bytes -= len(removed)
        self.assets[url] = (monotonic() + 900, data)
        self.asset_bytes += len(data)
        return data

    async def render(self, gameplay, display, member):
        avatar = member.display_avatar.with_size(128).with_static_format("png")
        avatar_url = str(avatar)
        key = (
            gameplay.internal_id,
            gameplay.rarity_stars,
            gameplay.class_name,
            tuple(gameplay.traits),
            gameplay.passive,
            gameplay.image_disabled,
            display.provider_id,
            display.name,
            display.native_name,
            display.series,
            display.image_url,
            avatar_url,
            member.display_name,
        )
        async with self.gate:
            self.card_bytes -= self._prune(self.cards, monotonic())
            if key in self.cards:
                self.cards.move_to_end(key)
                return self.cards[key][1]
            portrait, avatar = await asyncio.gather(
                (
                    self._download(display.image_url, character=True)
                    if not gameplay.image_disabled
                    else asyncio.sleep(0, result=None)
                ),
                self._download(avatar_url),
            )
            result = await image_work(
                render_summon_card, gameplay, display, portrait, avatar, member.display_name
            )
            if len(result) <= 8 * 1024 * 1024:
                while self.cards and (
                    self.card_bytes + len(result) > 12 * 1024 * 1024 or len(self.cards) >= 16
                ):
                    _, (_, removed) = self.cards.popitem(last=False)
                    self.card_bytes -= len(removed)
                # Failed CDN reads can recover promptly; don't cache missing art
                # for the same five minutes as a healthy completed card.
                ttl = 300 if (portrait or gameplay.image_disabled) and avatar else 15
                self.cards[key] = (monotonic() + ttl, result)
                self.card_bytes += len(result)
            return result
