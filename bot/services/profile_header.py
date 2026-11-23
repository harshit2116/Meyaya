"""Small cached profile illustrations; live relationship data stays native text."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Sequence
from io import BytesIO
from time import monotonic
from typing import Protocol, cast

from PIL import Image, ImageDraw, ImageFont, ImageOps

from bot.services.aura_archive import _asset as _raw_asset
from bot.services.aura_archive import _serif as _raw_serif
from bot.services.aura_archive import _text as _raw_text
from bot.services.callingcard_archive import _clean_title as _raw_clean_title
from bot.services.callingcard_archive import _icon as _raw_icon
from bot.services.callingcard_archive import _portrait_frame as _raw_portrait_frame
from bot.services.duostyle_archive import _hex as _raw_hex
from bot.services.duostyle_archive import _mix as _raw_mix
from bot.services.duostyle_archive import _rgb as _raw_rgb
from bot.services.duostyle_archive import theme as _raw_theme
from bot.services.profile_aesthetic import ProfileVisual
from bot.utils.image_work import BoundedImageGate, image_work

type _Font = ImageFont.FreeTypeFont | ImageFont.ImageFont


class _TextFn(Protocol):
    def __call__(
        self,
        draw: ImageDraw.ImageDraw,
        box: tuple[int, int, int, int],
        value: object,
        size: int,
        color: str,
        *,
        minimum: int = 20,
        serif: bool = True,
    ) -> None: ...


_asset = cast(Callable[[bytes | None], Image.Image | None], _raw_asset)
_serif = cast(Callable[[int], _Font], _raw_serif)
_text: _TextFn = _raw_text
_clean_title = cast(Callable[[str], str], _raw_clean_title)
_icon = cast(Callable[[str, str], Image.Image], _raw_icon)
_portrait_frame = cast(Callable[[str, str], Image.Image], _raw_portrait_frame)
_rgb = cast(Callable[[str], tuple[int, int, int]], _raw_rgb)
_hex = cast(Callable[[tuple[int, int, int]], str], _raw_hex)
_mix = cast(
    Callable[[tuple[int, int, int], tuple[int, int, int], float], tuple[int, int, int]],
    _raw_mix,
)
theme = cast(Callable[[tuple[str, ...]], tuple[str, str]], _raw_theme)


def render_header(visual: ProfileVisual, titles: Sequence[str]) -> bytes:
    accent, secondary = theme(visual.palette)
    background = _hex(_mix(_rgb(visual.palette[3]), (12, 13, 19), 0.95))
    image = Image.new("RGBA", (1140, 400), background)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((2, 2, 1137, 397), radius=26, outline=secondary, width=2)
    draw.rounded_rectangle((2, 18, 8, 382), radius=3, fill=accent)
    draw.text((36, 30), "M E Y A Y A ’ S   P R O F I L E", font=_serif(20), fill=accent)
    _text(draw, (36, 82, 660, 118), visual.name, 90, "#fff0f4", minimum=28)
    draw.rounded_rectangle((38, 218, 185, 258), radius=12, fill=secondary)
    draw.text((54, 226), visual.palette[0].upper(), font=_serif(21), fill="#fff0f4")
    if visual.server_tag:
        _text(draw, (207, 225, 440, 32), visual.server_tag, 22, accent, minimum=16)
    clean_titles = tuple(filter(None, (_clean_title(value) for value in titles)))
    width = min(224, (666 - 12 * (max(1, len(clean_titles)) - 1)) / max(1, len(clean_titles)))
    for index, title in enumerate(clean_titles[:3]):
        x = round(36 + index * (width + 12))
        draw.rounded_rectangle(
            (x, 292, x + width, 352),
            radius=14,
            fill=_hex(_mix(_rgb(secondary), _rgb(background), 0.6)),
            outline=accent,
        )
        kind = (
            "crown"
            if "parent" in title.lower()
            else "people" if "circle" in title.lower() else "heart"
        )
        image.alpha_composite(
            _icon(kind, accent).resize((30, 30), Image.Resampling.LANCZOS), (x + 12, 307)
        )
        _text(
            ImageDraw.Draw(image),
            (x + 50, 308, round(width - 60), 30),
            title,
            21,
            "#fff0f4",
            minimum=13,
        )
    art = _asset(visual.avatar)
    if art is None:
        art = Image.new("RGBA", (360, 360), visual.palette[3])
        ImageDraw.Draw(art).text(
            (180, 180), visual.name[:1] or "?", font=_serif(110), anchor="mm", fill=accent
        )
    art = ImageOps.fit(art, (360, 360), method=Image.Resampling.LANCZOS)
    mask = Image.new("L", (360, 360))
    ImageDraw.Draw(mask).ellipse((0, 0, 359, 359), fill=255)
    image.paste(art, (750, 20), mask)
    image.alpha_composite(
        _portrait_frame(accent, secondary).resize((470, 470), Image.Resampling.LANCZOS), (695, -22)
    )
    decoration = _asset(visual.decoration)
    if decoration is not None:
        decoration = ImageOps.contain(decoration, (390, 390), Image.Resampling.LANCZOS)
        image.alpha_composite(
            decoration, (930 - decoration.width // 2, 200 - decoration.height // 2)
        )
    output = BytesIO()
    image.convert("RGB").save(output, "PNG", compress_level=3)
    return output.getvalue()


class ProfileHeaderRenderer:
    """Coalesce repeated renders; retain at most 16 PNGs and 4 MiB for 5 minutes."""

    def __init__(self, max_bytes: int = 4 * 1024 * 1024, ttl: int = 300) -> None:
        self.cache: OrderedDict[tuple[object, ...], tuple[float, bytes]] = OrderedDict()
        self.bytes = 0
        self.max_bytes = max_bytes
        self.ttl = ttl
        self.gate = BoundedImageGate()

    async def render(self, visual: ProfileVisual, titles: Sequence[str]) -> bytes:
        key: tuple[object, ...] = (
            visual.asset_fingerprint,
            visual.name,
            visual.palette,
            visual.server_tag,
            hash(visual.avatar),
            hash(visual.decoration),
            tuple(titles),
        )
        async with self.gate:
            for old_key, (created, data) in list(self.cache.items()):
                if monotonic() - created >= self.ttl:
                    del self.cache[old_key]
                    self.bytes -= len(data)
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key][1]
            data = await image_work(render_header, visual, tuple(titles))
            if len(data) <= self.max_bytes:
                while self.cache and (
                    self.bytes + len(data) > self.max_bytes or len(self.cache) >= 16
                ):
                    _, (_, removed) = self.cache.popitem(last=False)
                    self.bytes -= len(removed)
                self.cache[key] = (monotonic(), data)
                self.bytes += len(data)
            return data
