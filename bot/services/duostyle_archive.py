"""Palette-adaptive Duo Style artwork, rendered locally with bounded ornament caches."""

from __future__ import annotations

import colorsys
from collections.abc import Sequence
from functools import lru_cache
import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps
from bot.services.card_renderer import CardFont, font
from bot.services.aura_archive import _asset, _serif, _spark

type RGB = tuple[int, int, int]

SIZE = (1600, 900)
PORTRAIT_SIZE = 320
PORTRAIT_Y = 163
LEFT_X, RIGHT_X = 179, 1101
LEFT_CX = LEFT_X + PORTRAIT_SIZE // 2
RIGHT_CX = RIGHT_X + PORTRAIT_SIZE // 2
PORTRAIT_CY = PORTRAIT_Y + PORTRAIT_SIZE // 2
SWATCH_Y = 626
SWATCH_STEP = 96
SWATCH_START_OFFSET = -144


def _rgb(color: str) -> RGB:
    raw = bytes.fromhex(color.lstrip("#"))
    return (raw[0], raw[1], raw[2])


def _hex(rgb: RGB) -> str:
    r, g, b = (round(max(0, min(255, v))) for v in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def _mix(a: RGB, b: RGB, amount: float) -> RGB:
    return (
        round(a[0] + (b[0] - a[0]) * amount),
        round(a[1] + (b[1] - a[1]) * amount),
        round(a[2] + (b[2] - a[2]) * amount),
    )


def theme(palette: Sequence[str]) -> tuple[str, str]:
    base = _rgb(palette[0])
    if colorsys.rgb_to_hsv(base[0] / 255, base[1] / 255, base[2] / 255)[1] < 0.16:
        base = next(
            (
                rgb_val
                for color in palette[:4]
                if colorsys.rgb_to_hsv(
                    (rgb_val := _rgb(color))[0] / 255, rgb_val[1] / 255, rgb_val[2] / 255
                )[1]
                > 0.18
            ),
            base,
        )
    # Keep recognisable colour in pale profiles and lift only very dark tones.
    accent = _mix(base, (247, 237, 248), 0.22 if sum(base) / 3 > 110 else 0.45)
    secondary = _mix(_rgb(palette[min(3, len(palette) - 1)]), accent, 0.35)
    return _hex(accent), _hex(secondary)


def palette_tags(palette: Sequence[str]) -> tuple[str, str, str, str]:
    colors = [_rgb(color) for color in palette[:4]]
    hsv = [colorsys.rgb_to_hsv(c[0] / 255, c[1] / 255, c[2] / 255) for c in colors]
    h, s, _ = hsv[0]
    if s < 0.13:
        h, s, _ = next((color for color in hsv if color[1] > 0.18), hsv[0])
    saturation = sum(v[1] for v in hsv) / len(hsv)
    value = sum(v[2] for v in hsv) / len(hsv)
    hue = (
        "Rose"
        if h >= 0.90 or h < 0.04
        else "Warm" if h < 0.18 else "Green" if h < 0.47 else "Blue" if h < 0.72 else "Violet"
    )
    return (
        hue if s > 0.13 else "Neutral",
        "Muted" if saturation < 0.3 else "Vivid" if saturation > 0.65 else "Balanced",
        "Bright" if value > 0.78 else "Deep" if value < 0.43 else "Mid-tone",
        "Contrast" if max(v[2] for v in hsv) - min(v[2] for v in hsv) > 0.4 else "Tonal",
    )


@lru_cache(maxsize=1)
def _neutral_art() -> Image.Image:
    path = Path(__file__).resolve().parents[1] / "assets/profile/duostyle/convergence-overlay.png"
    with Image.open(path) as source:
        return source.convert("RGBA").resize(SIZE, Image.Resampling.LANCZOS)


@lru_cache(maxsize=1)
def _ornament_source() -> tuple[Image.Image, Image.Image]:
    """One neutral half-frame, independently tinted for each member."""
    layer = _neutral_art().crop((0, 0, 800, 900)).copy()
    alpha = layer.getchannel("A")
    # Mask out the upper-center pendant (composed once in _sync_emblem) while
    # preserving the continuous outer top border and bottom convergence capsule.
    mask = Image.new("L", (800, 900), 255)
    ImageDraw.Draw(mask).rectangle((595, 110, 799, 312), fill=0)
    alpha = ImageChops.multiply(alpha, mask)
    return ImageOps.grayscale(layer), alpha


@lru_cache(maxsize=4)
def _side_ornaments(accent: str, secondary: str) -> Image.Image:
    """Four palette variants at most; no member images are retained in this cache."""
    luminance, alpha = _ornament_source()
    shadow = _hex(_mix(_rgb(secondary), (26, 19, 34), 0.55))
    highlight = _hex(_mix(_rgb(accent), (255, 244, 248), 0.62))
    layer = ImageOps.colorize(luminance, shadow, highlight, mid=accent, midpoint=142).convert(
        "RGBA"
    )
    layer.putalpha(alpha)
    return layer


@lru_cache(maxsize=1)
def _portrait_mask() -> Image.Image:
    mask = Image.new("L", (PORTRAIT_SIZE, PORTRAIT_SIZE))
    ImageDraw.Draw(mask).ellipse((0, 0, PORTRAIT_SIZE - 1, PORTRAIT_SIZE - 1), fill=255)
    return mask


@lru_cache(maxsize=2)
def _shard_geometry(
    mirrored: bool,
) -> tuple[tuple[int, int, Image.Image, tuple[tuple[int, int], ...]], ...]:
    shapes: tuple[tuple[tuple[int, int], ...], ...] = (
        ((22, 42), (162, 108), (181, 590), (10, 662)),
    )
    result: list[tuple[int, int, Image.Image, tuple[tuple[int, int], ...]]] = []
    for points in shapes:
        pts: tuple[tuple[int, int], ...] = (
            tuple((1600 - x, y) for x, y in points) if mirrored else points
        )
        x = min(p[0] for p in pts)
        y = min(p[1] for p in pts)
        width = max(p[0] for p in pts) - x + 1
        height = max(p[1] for p in pts) - y + 1
        mask = Image.new("L", (width, height))
        ImageDraw.Draw(mask).polygon([(px - x, py - y) for px, py in pts], fill=115)
        result.append((x, y, mask, pts))
    return tuple(result)


def _reflections(image: Image.Image, art: Image.Image, accent: str, mirrored: bool) -> None:
    reflected = ImageOps.mirror(art)
    for x, y, mask, points in _shard_geometry(mirrored):
        fragment = ImageOps.fit(
            reflected, (mask.width * 2, mask.height), method=Image.Resampling.LANCZOS
        )
        fragment = fragment.resize(mask.size, Image.Resampling.LANCZOS)
        image.paste(fragment, (x, y), mask)
        ImageDraw.Draw(image).line([*points, points[0]], fill=accent, width=1)


def _portrait(image: Image.Image, visual: Any, x: int, accent: str, mirrored: bool) -> None:
    _ = mirrored
    art = _asset(visual.avatar)
    if art is None:
        art = Image.new("RGBA", (PORTRAIT_SIZE, PORTRAIT_SIZE), visual.palette[3])
        ImageDraw.Draw(art).text(
            (PORTRAIT_SIZE / 2, PORTRAIT_SIZE / 2),
            visual.name[:1] or "?",
            font=_serif(96),
            anchor="mm",
            fill="#fff4f7",
        )
    art = ImageOps.fit(art, (PORTRAIT_SIZE, PORTRAIT_SIZE), method=Image.Resampling.LANCZOS)
    # Soft circular glow behind the portrait bezel so light and dark avatars alike pop cleanly.
    halo = Image.new("RGBA", (PORTRAIT_SIZE + 80, PORTRAIT_SIZE + 80), (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse(
        (24, 24, PORTRAIT_SIZE + 56, PORTRAIT_SIZE + 56), fill=(*_rgb(accent), 46)
    )
    halo = halo.filter(ImageFilter.GaussianBlur(18))
    image.alpha_composite(halo, (x - 40, PORTRAIT_Y - 40))
    image.paste(art, (x, PORTRAIT_Y), _portrait_mask())
    decoration = _asset(visual.decoration)
    if decoration is not None:
        decoration = ImageOps.contain(decoration, (356, 356), Image.Resampling.LANCZOS)
        image.alpha_composite(
            decoration,
            (
                x + (PORTRAIT_SIZE - decoration.width) // 2,
                PORTRAIT_Y + (PORTRAIT_SIZE - decoration.height) // 2,
            ),
        )


def _centred(
    draw: ImageDraw.ImageDraw,
    text: object,
    cx: float,
    y: float,
    width: float,
    size: int,
    color: str,
    *,
    serif: bool = False,
    lines: int = 1,
    anchor: str = "ma",
) -> None:
    value = " ".join(str(text).split())[:180]
    family = _serif if serif and all(ord(c) < 0x3000 for c in value) else font
    while True:
        chosen = family(size)
        words = value.split()
        rows: list[str] = []
        row = ""
        for word in words:
            test = (row + " " + word).strip()
            if row and draw.textlength(test, font=chosen) > width:
                rows.append(row)
                row = word
            else:
                row = test
        rows.append(row)
        if size <= 14 or (
            len(rows) <= lines and all(draw.textlength(row, font=chosen) <= width for row in rows)
        ):
            break
        size -= 1
    shown = rows[:lines]
    if anchor == "mm" and len(shown) > 1:
        step = size + 7
        top = y - (len(shown) - 1) * step / 2
        for i, row in enumerate(shown):
            while draw.textlength(row, font=chosen) > width and len(row) > 1:
                row = row[:-2] + "…"
            draw.text((cx, top + i * step), row, font=chosen, fill=color, anchor="mm")
        return
    for i, row in enumerate(shown):
        while draw.textlength(row, font=chosen) > width and len(row) > 1:
            row = row[:-2] + "…"
        draw.text((cx, y + i * (size + 7)), row, font=chosen, fill=color, anchor=anchor)


def _identity(image: Image.Image, visual: Any, x: int, accent: str) -> None:
    draw = ImageDraw.Draw(image)
    center = x + PORTRAIT_SIZE // 2
    border_soft = _hex(_mix(_rgb(accent), (28, 22, 38), 0.58))
    pill_fill = "#14101d"
    # Clean nameplate placed neatly below the portrait wreath (zero avatar overlap).
    draw.rounded_rectangle(
        (center - 178, 504, center + 178, 554),
        radius=25,
        fill=pill_fill,
        outline=accent,
        width=2,
    )
    draw.rounded_rectangle(
        (center - 173, 509, center + 173, 549),
        radius=20,
        outline=border_soft,
        width=1,
    )
    _spark(draw, center - 178, 529, 8, accent)
    _spark(draw, center + 178, 529, 8, accent)
    _centred(draw, visual.name, center, 528, 300, 30, "#fff4f9", serif=True, anchor="mm")
    if visual.server_tag:
        tag_w = min(116, round(draw.textlength(visual.server_tag, font=font(12))) + 26)
        draw.rounded_rectangle(
            (center - tag_w / 2, 546, center + tag_w / 2, 565),
            radius=9,
            fill="#34233b",
            outline=accent,
        )
        _centred(draw, visual.server_tag, center, 555, tag_w - 16, 12, "#f7dff2", anchor="mm")

    # Refined frosted-obsidian Profile Palette panel
    card_x0, card_x1 = center - 224, center + 224
    draw.rounded_rectangle(
        (card_x0, 570, card_x1, 694),
        radius=22,
        fill="#130f1c",
        outline=accent,
        width=1,
    )
    draw.rounded_rectangle(
        (card_x0 + 5, 575, card_x1 - 5, 689),
        radius=18,
        outline=border_soft,
        width=1,
    )
    draw.text(
        (center, 583),
        "P R O F I L E   P A L E T T E",
        font=font(12),
        anchor="ma",
        fill="#e5cce0",
    )
    swatches = (*visual.palette[:3], visual.palette[-1]) if visual.banner_swatch else visual.palette[:4]
    for i, color in enumerate(swatches):
        cx = center + SWATCH_START_OFFSET + i * SWATCH_STEP
        # Crisp outer ring + subtle contrast inner rim so white & obsidian swatches both stand out
        draw.ellipse((cx - 24, SWATCH_Y - 24, cx + 24, SWATCH_Y + 24), fill="#0a0810", outline=accent, width=2)
        draw.ellipse((cx - 21, SWATCH_Y - 21, cx + 21, SWATCH_Y + 21), fill=color)
    tags: tuple[str, ...] = palette_tags(visual.palette)
    if visual.banner_swatch:
        tags = (*tags[:3], "Banner")
    for i, tag in enumerate(tags):
        cx = center + SWATCH_START_OFFSET + i * SWATCH_STEP
        draw.rounded_rectangle(
            (cx - 43, 658, cx + 43, 682),
            radius=11,
            fill="#1e1729",
            outline=border_soft,
            width=1,
        )
        _centred(draw, tag, cx, 670, 76, 12, "#eedded", anchor="mm")


@lru_cache(maxsize=1)
def _score_font() -> CardFont:
    for path in (
        "C:/Windows/Fonts/timesbd.ttf",
        "C:/Windows/Fonts/palab.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    ):
        if Path(path).is_file():
            return ImageFont.truetype(path, 118)
    return _serif(118)


@lru_cache(maxsize=8)
def _sync_emblem(left_accent: str, right_accent: str) -> Image.Image:
    neutral = _neutral_art().crop((595, 104, 1005, 312))
    accent = _hex(_mix(_rgb(left_accent), _rgb(right_accent), 0.5))
    emblem = ImageOps.colorize(
        ImageOps.grayscale(neutral), "#271d30", "#fff4f9", mid=accent, midpoint=142
    ).convert("RGBA")
    emblem.putalpha(neutral.getchannel("A"))
    return emblem


@lru_cache(maxsize=4)
def _convergence_band(
    left_palette: tuple[str, ...], right_palette: tuple[str, ...]
) -> Image.Image:
    stops = [
        _rgb(left_palette[0]),
        _rgb(left_palette[2]),
        _mix(_rgb(left_palette[1]), _rgb(right_palette[1]), 0.5),
        _rgb(right_palette[2]),
        _rgb(right_palette[3]),
    ]
    band = Image.new("RGB", (1340, 1))
    colors: list[RGB] = []
    for x in range(1340):
        t = x / 1339 * 4
        index = min(3, int(t))
        colors.append(_mix(stops[index], stops[index + 1], t - index))
    band.putdata(colors)
    return band.resize((1340, 44)).convert("RGBA")


def _horizontal_gradient(width: int, height: int, left_hex: str, right_hex: str) -> Image.Image:
    a, b = _rgb(left_hex), _rgb(right_hex)
    strip = Image.new("RGB", (width, 1))
    strip.putdata([_mix(a, b, x / max(1, width - 1)) for x in range(width)])
    return strip.resize((width, height)).convert("RGBA")


def _convergence(
    image: Image.Image, left: Any, right: Any, left_accent: str, right_accent: str
) -> None:
    # Fit the luminous gradient bar cleanly inside the silver filigree capsule
    # (capsule inner opening: x=264..1344, y=738..807).
    bar_x, bar_y, bar_w, bar_h = 276, 751, 1048, 44
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (bar_x - 4, bar_y - 4, bar_x + bar_w + 4, bar_y + bar_h + 4),
        radius=26,
        fill="#0b0912",
    )
    band = _convergence_band(tuple(left.palette), tuple(right.palette)).resize(
        (bar_w, bar_h), Image.Resampling.LANCZOS
    )
    mask = Image.new("L", (bar_w, bar_h))
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, bar_w - 1, bar_h - 1), radius=22, fill=255)
    image.paste(band, (bar_x, bar_y), mask)
    # Fine crossing silk light threads unite both profile palettes smoothly.
    threads = Image.new("RGBA", SIZE)
    td = ImageDraw.Draw(threads)
    mid_y = bar_y + bar_h / 2
    for phase, color in ((0.0, left_accent), (math.pi, right_accent), (1.2, "#fff5fa")):
        points = [
            (bar_x + x, mid_y + math.sin(x / bar_w * math.tau * 1.7 + phase) * 16)
            for x in range(0, bar_w + 1, 5)
        ]
        td.line(points, fill=(*_rgb(color), 145), width=1)
    image.alpha_composite(threads)


def _name_badge(
    draw: ImageDraw.ImageDraw,
    name: str,
    x: int,
    y: int,
    accent: str,
    *,
    align_right: bool = False,
) -> None:
    label = " ".join(name.split())[:22].upper()
    f = font(12)
    text_w = draw.textlength(label, font=f)
    pad_l, pad_r = (14, 24) if align_right else (24, 14)
    box_w = min(220, round(text_w) + pad_l + pad_r)
    x0 = x - box_w if align_right else x
    x1 = x if align_right else x + box_w
    border = _hex(_mix(_rgb(accent), (24, 19, 34), 0.5))
    draw.rounded_rectangle((x0, y, x1, y + 24), radius=12, fill="#130f1c", outline=border, width=1)
    dot_x = x1 - 12 if align_right else x0 + 12
    draw.ellipse((dot_x - 4, y + 8, dot_x + 4, y + 16), fill=accent)
    text_cx = (x0 + x1 - 10) / 2 if align_right else (x0 + x1 + 10) / 2
    _centred(draw, label, text_cx, y + 12, box_w - 30, 12, "#f3e5f0", anchor="mm")


def render_duo(
    left: Any, right: Any, *, score: int, verdict: str, reason: str
) -> Image.Image:
    left_accent, left_secondary = theme(left.palette)
    right_accent, right_secondary = theme(right.palette)
    common = _hex(_mix(_rgb(left_accent), _rgb(right_accent), 0.5))
    image = Image.new("RGBA", SIZE, "#0d0b14")

    # Atmospheric dual-aura backdrop with clean center contrast
    glow = Image.new("RGBA", (400, 225), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-20, 10, 185, 195), fill=(*_rgb(left_accent), 36))
    gd.ellipse((215, 10, 420, 195), fill=(*_rgb(right_accent), 36))
    gd.ellipse((140, 58, 260, 165), fill=(*_rgb(common), 22))
    image.alpha_composite(
        glow.filter(ImageFilter.GaussianBlur(26)).resize(SIZE, Image.Resampling.BILINEAR)
    )

    # Portraits & convergence gradient sit cleanly behind the silver filigree frame
    _portrait(image, left, LEFT_X, left_accent, False)
    _portrait(image, right, RIGHT_X, right_accent, True)
    _convergence(image, left, right, left_accent, right_accent)

    # Colorized symmetrical silver filigree frame + upper-center celestial pendant
    image.alpha_composite(_side_ornaments(left_accent, left_secondary))
    image.alpha_composite(ImageOps.mirror(_side_ornaments(right_accent, right_secondary)), (800, 0))
    image.alpha_composite(_sync_emblem(left_accent, right_accent), (595, 104))

    # Nameplates & Profile Palette cards
    _identity(image, left, LEFT_X, left_accent)
    _identity(image, right, RIGHT_X, right_accent)

    draw = ImageDraw.Draw(image)

    # Dedicated top header band (y=18..96 - completely clear of portraits and outer border)
    duo_tint = _hex(_mix(_rgb(left_accent), (255, 240, 248), 0.35))
    _spark(draw, 58, 52, 13, duo_tint)
    draw.text((84, 24), "DUO", font=_serif(38), fill=duo_tint)
    duo_w = draw.textlength("DUO ", font=_serif(38))
    draw.text((84 + duo_w, 24), "STYLE", font=_serif(38), fill="#fff5fa")
    draw.text(
        (86, 70),
        "D I F F E R E N T   P A L E T T E S ,   S A M E   S T O R Y",
        font=font(10),
        fill="#ccb7d1",
    )
    draw.text((1534, 30), "M E Y A Y A", font=font(13), anchor="ra", fill="#ecd4e7")
    _spark(draw, 1548, 37, 5, common)
    draw.text((1554, 54), "STYLE ANALYSIS", font=font(10), anchor="ra", fill="#b69ec0")

    # Center Editorial Score Showcase (cx=800, y=312..690)
    draw.text((800, 316), "S T Y L E   S Y N C", font=_serif(17), anchor="ma", fill="#f3dae9")
    draw.text((800, 348), f"{score}%", font=_score_font(), anchor="ma", fill="#fff6fb")

    # Smooth dual-palette progress gauge
    gauge_x, gauge_y, gauge_w, gauge_h = 635, 480, 330, 12
    draw.rounded_rectangle(
        (gauge_x, gauge_y, gauge_x + gauge_w, gauge_y + gauge_h),
        radius=6,
        fill="#241c30",
        outline="#4a3958",
        width=1,
    )
    if score > 0:
        fill_w = max(12, round(gauge_w * score / 100))
        grad = _horizontal_gradient(fill_w, gauge_h, left_accent, right_accent)
        gmask = Image.new("L", (fill_w, gauge_h))
        ImageDraw.Draw(gmask).rounded_rectangle((0, 0, fill_w - 1, gauge_h - 1), radius=6, fill=255)
        image.paste(grad, (gauge_x, gauge_y), gmask)
    _spark(draw, gauge_x + gauge_w * score / 100, gauge_y + gauge_h / 2, 10, "#fff6fb")

    # Verdict badge & reason copy
    verdict_border = _hex(_mix(_rgb(common), (44, 34, 56), 0.35))
    draw.rounded_rectangle(
        (618, 514, 982, 570),
        radius=18,
        fill="#161120",
        outline=verdict_border,
        width=1,
    )
    _centred(draw, verdict, 800, 542, 332, 19, "#f7e8f3", lines=2, anchor="mm")
    draw.line((666, 594, 934, 594), fill="#6d5270")
    _spark(draw, 800, 594, 8, common)
    _centred(draw, reason, 800, 616, 360, 19, "#dfd0e5", lines=3)

    # High-contrast labels for bottom Color Convergence capsule (clear of outer filigree petals)
    _name_badge(draw, left.name, 342, 706, left_accent, align_right=False)
    _name_badge(draw, right.name, 1258, 706, right_accent, align_right=True)
    draw.rounded_rectangle(
        (648, 705, 952, 731),
        radius=13,
        fill="#130f1c",
        outline=_hex(_mix(_rgb(common), (28, 22, 38), 0.5)),
        width=1,
    )
    draw.text(
        (800, 718),
        "C O L O R   C O N V E R G E N C E",
        font=font(12),
        anchor="mm",
        fill="#f0c8df",
    )
    _spark(draw, 800, 773, 14, "#fff6fb")

    # Crisp unobstructed footer bar (y=860..892)
    draw.text((46, 872), "P R O F I L E   S T U D I O", font=font(10), anchor="lm", fill="#9d87a8")
    draw.text(
        (800, 872),
        "M E Y A Y A   ·   D U O   A N A L Y S I S",
        font=font(11),
        anchor="mm",
        fill="#cbb0c8",
    )
    draw.text(
        (1554, 872),
        "T W O   S T Y L E S ,   O N E   V I B E",
        font=font(10),
        anchor="rm",
        fill="#9d87a8",
    )
    return image
