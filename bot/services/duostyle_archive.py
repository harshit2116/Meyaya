"""Palette-adaptive Duo Style artwork, rendered locally with bounded ornament caches."""

from __future__ import annotations

import colorsys
from functools import lru_cache
import math
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps
from bot.services.card_renderer import font
from bot.services.aura_archive import _asset, _serif, _spark

SIZE = (1600, 900)
PORTRAIT_SIZE = 484


def _rgb(color):
    return tuple(bytes.fromhex(color.lstrip("#")))


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(round(max(0, min(255, v))) for v in rgb)


def _mix(a, b, amount):
    return tuple(round(x + (y - x) * amount) for x, y in zip(a, b))


def theme(palette):
    base = _rgb(palette[0])
    if colorsys.rgb_to_hsv(*(v / 255 for v in base))[1] < 0.16:
        base = next(
            (
                _rgb(color)
                for color in palette[:4]
                if colorsys.rgb_to_hsv(*(v / 255 for v in _rgb(color)))[1] > 0.18
            ),
            base,
        )
    # Keep recognisable colour in pale profiles and lift only very dark tones.
    accent = _mix(base, (247, 237, 248), 0.22 if sum(base) / 3 > 110 else 0.45)
    secondary = _mix(_rgb(palette[min(3, len(palette) - 1)]), accent, 0.35)
    return _hex(accent), _hex(secondary)


def palette_tags(palette):
    colors = [_rgb(color) for color in palette[:4]]
    hsv = [colorsys.rgb_to_hsv(*(v / 255 for v in color)) for color in colors]
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
def _ornament_source():
    """Decode neutral production artwork once, retaining its genuine transparency."""
    path = Path(__file__).resolve().parents[1] / "assets/profile/duostyle/floral-overlay.png"
    with Image.open(path) as source:
        art = source.convert("RGBA").resize(SIZE, Image.Resampling.LANCZOS)
    # Align the generated frame window with the live portrait. Only the left
    # half is needed: the other member gets an independently tinted mirror.
    layer = Image.new("RGBA", (800, 900))
    layer.alpha_composite(art.crop((0, 0, 800, 900)), (-62, -17))
    alpha = layer.getchannel("A")
    # Keep typography clear and suppress the central arch above the score.
    vertical_fade = Image.new("L", (1, 900))
    values = []
    for y in range(900):
        opacity = min(1.0, max(0, (y - 77) / 38), max(0, (687 - y) / 45))
        opacity *= 0.62 + 0.38 * min(1, max(0, (y - 360) / 160))
        values.append(round(255 * opacity))
    vertical_fade.putdata(values)
    horizontal_fade = Image.new("L", (800, 1))
    horizontal_fade.putdata([round(255 * min(1, max(0, (650 - x) / 55))) for x in range(800)])
    fade = ImageChops.multiply(vertical_fade.resize(layer.size), horizontal_fade.resize(layer.size))
    alpha = ImageChops.multiply(alpha, fade)
    return ImageOps.grayscale(layer), alpha


@lru_cache(maxsize=4)
def _side_ornaments(accent, secondary):
    """Four palette variants at most; no member images are retained in this cache."""
    luminance, alpha = _ornament_source()
    shadow = _hex(_mix(_rgb(secondary), (20, 13, 25), 0.62))
    highlight = _hex(_mix(_rgb(accent), (255, 239, 240), 0.5))
    layer = ImageOps.colorize(luminance, shadow, highlight, mid=accent, midpoint=164).convert(
        "RGBA"
    )
    layer.putalpha(alpha)
    return layer


@lru_cache(maxsize=1)
def _portrait_mask():
    mask = Image.new("L", (PORTRAIT_SIZE, PORTRAIT_SIZE))
    ImageDraw.Draw(mask).ellipse((0, 0, PORTRAIT_SIZE - 1, PORTRAIT_SIZE - 1), fill=255)
    return mask


@lru_cache(maxsize=2)
def _shard_geometry(mirrored):
    shapes = (
        ((43, 187), (125, 167), (134, 349), (43, 426)),
        ((44, 451), (122, 394), (135, 591), (55, 650)),
    )
    result = []
    for points in shapes:
        points = tuple((1600 - x, y) for x, y in points) if mirrored else points
        x = min(p[0] for p in points)
        y = min(p[1] for p in points)
        width = max(p[0] for p in points) - x + 1
        height = max(p[1] for p in points) - y + 1
        mask = Image.new("L", (width, height))
        ImageDraw.Draw(mask).polygon([(px - x, py - y) for px, py in points], fill=115)
        result.append((x, y, mask, points))
    return tuple(result)


def _reflections(image, art, accent, mirrored):
    reflected = ImageOps.mirror(art)
    for x, y, mask, points in _shard_geometry(mirrored):
        fragment = ImageOps.fit(reflected, mask.size, method=Image.Resampling.LANCZOS)
        image.paste(fragment, (x, y), mask)
        ImageDraw.Draw(image).line([*points, points[0]], fill=accent, width=1)


def _portrait(image, visual, x, accent, mirrored):
    art = _asset(visual.avatar)
    if art is None:
        art = Image.new("RGBA", (484, 484), visual.palette[3])
        ImageDraw.Draw(art).text(
            (242, 242), visual.name[:1] or "?", font=_serif(110), anchor="mm", fill="#fff4f7"
        )
    art = ImageOps.fit(art, (484, 484), method=Image.Resampling.LANCZOS)
    _reflections(image, art, accent, mirrored)
    image.paste(art, (x, 126), _portrait_mask())
    decoration = _asset(visual.decoration)
    if decoration is not None:
        decoration = ImageOps.contain(decoration, (522, 522), Image.Resampling.LANCZOS)
        image.alpha_composite(
            decoration, (x + (484 - decoration.width) // 2, 126 + (484 - decoration.height) // 2)
        )


def _centred(draw, text, cx, y, width, size, color, *, serif=False, lines=1):
    text = " ".join(str(text).split())[:180]
    family = _serif if serif and all(ord(c) < 0x3000 for c in text) else font
    while True:
        chosen = family(size)
        words = text.split()
        rows = []
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
    for i, row in enumerate(rows[:lines]):
        while draw.textlength(row, font=chosen) > width and len(row) > 1:
            row = row[:-2] + "…"
        draw.text((cx, y + i * (size + 7)), row, font=chosen, fill=color, anchor="ma")


def _identity(image, visual, x, accent):
    draw = ImageDraw.Draw(image)
    center = x + 242
    draw.rounded_rectangle(
        (center - 174, 531, center + 174, 611), radius=30, fill="#16121b", outline=accent, width=1
    )
    _spark(draw, center - 175, 571, 12, accent)
    _spark(draw, center + 175, 571, 12, accent)
    _centred(
        draw, visual.name, center, 543 if visual.server_tag else 553, 306, 34, "#fff1f7", serif=True
    )
    if visual.server_tag:
        _centred(draw, visual.server_tag, center, 586, 300, 13, accent)
    draw.rounded_rectangle(
        (x - 12, 625, x + 496, 789),
        radius=25,
        fill="#1b1520",
        outline=_hex(_mix(_rgb(accent), (23, 18, 29), 0.55)),
        width=1,
    )
    draw.text(
        (center, 643), "P R O F I L E  P A L E T T E", font=font(13), anchor="ma", fill="#d9c8d9"
    )
    for i, color in enumerate(visual.palette[:4]):
        cx = center - 126 + i * 84
        draw.ellipse((cx - 24, 672, cx + 24, 720), fill=color, outline=accent, width=1)
    for i, tag in enumerate(palette_tags(visual.palette)):
        bx = x + 5 + i * 121
        draw.rounded_rectangle(
            (bx, 742, bx + 111, 772), radius=15, fill="#261c2c", outline=accent, width=1
        )
        _centred(draw, "# " + tag, bx + 55, 748, 100, 14, "#efdfed")


@lru_cache(maxsize=1)
def _score_font():
    for path in (
        "C:/Windows/Fonts/georgiai.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
    ):
        if Path(path).is_file():
            return ImageFont.truetype(path, 124)
    return _serif(124)


@lru_cache(maxsize=8)
def _heart_layer(left_accent, right_accent):
    heart = Image.new("RGBA", (500, 300))
    draw = ImageDraw.Draw(heart)
    for offset, angle, color in ((-38, -0.38, left_accent), (38, 0.38, right_accent)):
        points = []
        for i in range(301):
            t = i * math.tau / 300
            px = 16 * math.sin(t) ** 3 * 4.1
            py = (
                -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
                * 4.1
            )
            points.append(
                (
                    250 + offset + px * math.cos(angle) - py * math.sin(angle),
                    127 + px * math.sin(angle) + py * math.cos(angle),
                )
            )
        draw.line(points, fill=color, width=5)
    glow = heart.filter(ImageFilter.GaussianBlur(13))
    glow = ImageChops.add(glow, glow)
    glow.alpha_composite(heart)
    return glow.resize((250, 150), Image.Resampling.LANCZOS)


def render_duo(left, right, *, score, verdict, reason):
    left_accent, left_secondary = theme(left.palette)
    right_accent, right_secondary = theme(right.palette)
    common = _hex(_mix(_rgb(left_accent), _rgb(right_accent), 0.5))
    image = Image.new("RGBA", SIZE, "#100e17")
    # Small glow buffers avoid full-canvas blur work for every profile pair.
    glow = Image.new("RGBA", (400, 225))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-70, 15, 175, 245), fill=(*_rgb(left_accent), 42))
    gd.ellipse((225, 15, 470, 245), fill=(*_rgb(right_accent), 42))
    image.alpha_composite(
        glow.filter(ImageFilter.GaussianBlur(24)).resize(SIZE, Image.Resampling.BILINEAR)
    )
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((20, 18, 1580, 880), radius=28, outline="#54404f", width=1)
    draw.line((53, 826, 1547, 826), fill="#6b4d62", width=1)
    draw.text((81, 35), "DUO", font=_serif(39), fill=left_accent)
    draw.text((195, 35), "STYLE", font=_serif(39), fill="#f9eff7")
    draw.text((83, 86), "Different palettes, same story.", font=font(15), fill="#bdacbf")
    draw.line((393, 62, 1450, 62), fill="#604257", width=1)
    _spark(draw, 800, 62, 13, common)
    draw.text((1510, 44), "M E Y A Y A", font=font(14), anchor="ra", fill="#d5bed4")
    draw.text((1510, 67), "STYLE ANALYSIS", font=font(11), anchor="ra", fill="#b49bb4")
    _portrait(image, left, 94, left_accent, False)
    _portrait(image, right, 1022, right_accent, True)
    image.alpha_composite(_side_ornaments(left_accent, left_secondary))
    image.alpha_composite(ImageOps.mirror(_side_ornaments(right_accent, right_secondary)), (800, 0))
    _identity(image, left, 94, left_accent)
    _identity(image, right, 1022, right_accent)
    draw = ImageDraw.Draw(image)
    image.alpha_composite(_heart_layer(left_accent, right_accent), (675, 139))
    draw = ImageDraw.Draw(image)
    draw.text((800, 286), "S T Y L E  S Y N C", font=font(18), anchor="ma", fill="#dec6dc")
    draw.text((800, 320), f"{score}%", font=_score_font(), anchor="ma", fill="#fff0f7")
    draw.rounded_rectangle((650, 465, 950, 478), radius=6, fill="#4c4055")
    if score > 0:
        draw.rounded_rectangle(
            (650, 465, 650 + max(13, 300 * score / 100), 478), radius=6, fill=common
        )
    _spark(draw, 650 + 300 * score / 100, 471, 8, "#fff0f6")
    draw.rounded_rectangle(
        (646, 516, 954, 602), radius=20, fill="#1b1520", outline="#74566d", width=1
    )
    _centred(draw, verdict, 800, 535, 270, 21, "#f1e2ef", lines=2)
    draw.line((684, 633, 916, 633), fill="#7b566e", width=1)
    _spark(draw, 800, 633, 10, common)
    _centred(draw, reason, 800, 661, 279, 19, "#d6c5d7", lines=3)
    for i in range(5):
        cx = 752 + i * 24
        draw.ellipse(
            (cx - 4, 771, cx + 4, 779),
            outline=common,
            fill=common if i == 2 else "#201822",
            width=1,
        )
    draw.text((51, 852), "M E Y A Y A  /  D U O  A N A L Y S I S", font=font(12), fill="#ad92aa")
    draw.text(
        (1547, 852),
        "T W O  S T Y L E S ,  O N E  V I B E .",
        font=font(12),
        anchor="ra",
        fill="#ad92aa",
    )
    _spark(draw, 800, 851, 8, common)
    return image
