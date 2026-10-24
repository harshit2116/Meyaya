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
PORTRAIT_SIZE = 430
PORTRAIT_Y = 100
LEFT_X, RIGHT_X = 215, 955


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
def _neutral_art():
    path = Path(__file__).resolve().parents[1] / "assets/profile/duostyle/convergence-overlay.png"
    with Image.open(path) as source:
        return source.convert("RGBA").resize(SIZE, Image.Resampling.LANCZOS)


@lru_cache(maxsize=1)
def _ornament_source():
    """One neutral half-frame, independently tinted for each member."""
    layer = Image.new("RGBA", (800, 900))
    layer.alpha_composite(_neutral_art().crop((0, 0, 800, 900)), (-19, -8))
    # The middle jewel is composed once, independently of the two side frames.
    fade = Image.new("L", (800, 1))
    fade.putdata([round(255 * min(1, max(0, (792 - x) / 82))) for x in range(800)])
    alpha = ImageChops.multiply(layer.getchannel("A"), fade.resize(layer.size))
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
    # Keep glass and metal luminous without washing out the member portraits.
    opacity = Image.new("L", (800, 1))
    opacity.putdata([160 if x < 190 else 208 for x in range(800)])
    layer.putalpha(ImageChops.multiply(alpha, opacity.resize(layer.size)))
    return layer


@lru_cache(maxsize=1)
def _portrait_mask():
    mask = Image.new("L", (PORTRAIT_SIZE, PORTRAIT_SIZE))
    ImageDraw.Draw(mask).ellipse((0, 0, PORTRAIT_SIZE - 1, PORTRAIT_SIZE - 1), fill=255)
    return mask


@lru_cache(maxsize=2)
def _shard_geometry(mirrored):
    shapes = (((22, 42), (162, 108), (181, 590), (10, 662)),)
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
        fragment = ImageOps.fit(
            reflected, (mask.width * 2, mask.height), method=Image.Resampling.LANCZOS
        )
        fragment = fragment.resize(mask.size, Image.Resampling.LANCZOS)
        image.paste(fragment, (x, y), mask)
        ImageDraw.Draw(image).line([*points, points[0]], fill=accent, width=1)


def _portrait(image, visual, x, accent, mirrored):
    art = _asset(visual.avatar)
    if art is None:
        art = Image.new("RGBA", (PORTRAIT_SIZE, PORTRAIT_SIZE), visual.palette[3])
        ImageDraw.Draw(art).text(
            (PORTRAIT_SIZE / 2, PORTRAIT_SIZE / 2),
            visual.name[:1] or "?",
            font=_serif(110),
            anchor="mm",
            fill="#fff4f7",
        )
    art = ImageOps.fit(art, (PORTRAIT_SIZE, PORTRAIT_SIZE), method=Image.Resampling.LANCZOS)
    _reflections(image, art, accent, mirrored)
    image.paste(art, (x, PORTRAIT_Y), _portrait_mask())
    decoration = _asset(visual.decoration)
    if decoration is not None:
        decoration = ImageOps.contain(decoration, (468, 468), Image.Resampling.LANCZOS)
        image.alpha_composite(
            decoration,
            (
                x + (PORTRAIT_SIZE - decoration.width) // 2,
                PORTRAIT_Y + (PORTRAIT_SIZE - decoration.height) // 2,
            ),
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
    center = x + PORTRAIT_SIZE // 2
    draw.rounded_rectangle(
        (center - 151, 450, center + 151, 511), radius=24, fill="#181019", outline=accent, width=2
    )
    _spark(draw, center - 151, 480, 10, accent)
    _spark(draw, center + 151, 480, 10, accent)
    _centred(draw, visual.name, center, 457, 276, 35, "#fff1f7", serif=True)
    if visual.server_tag:
        width = min(116, round(draw.textlength(visual.server_tag, font=font(13))) + 30)
        draw.rounded_rectangle(
            (center - width / 2, 503, center + width / 2, 523),
            radius=6,
            fill="#50354e",
            outline=accent,
        )
        _centred(draw, visual.server_tag, center, 506, width - 18, 13, "#f6d9ef")
    draw.rounded_rectangle(
        (x - 5, 531, x + PORTRAIT_SIZE + 5, 676), radius=24, fill="#16121c", outline=accent, width=1
    )
    draw.rounded_rectangle(
        (x + 2, 537, x + PORTRAIT_SIZE - 2, 670),
        radius=20,
        outline=_hex(_mix(_rgb(accent), (23, 18, 29), 0.6)),
    )
    draw.text(
        (center, 548), "P R O F I L E  P A L E T T E", font=font(13), anchor="ma", fill="#e4cadd"
    )
    for i, color in enumerate(visual.palette[:4]):
        cx = center - 145 + i * 97
        draw.ellipse((cx - 26, 576, cx + 26, 628), fill=color, outline=accent)
    for i, tag in enumerate(palette_tags(visual.palette)):
        bx = x + 11 + i * 103
        draw.rounded_rectangle((bx, 640, bx + 98, 665), radius=9, fill="#251c2a", outline=accent)
        _centred(draw, "# " + tag, bx + 49, 645, 89, 13, "#f0dfee")


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
def _sync_emblem(left_accent, right_accent):
    neutral = _neutral_art().crop((700, 0, 900, 261))
    accent = _hex(_mix(_rgb(left_accent), _rgb(right_accent), 0.5))
    emblem = ImageOps.colorize(
        ImageOps.grayscale(neutral), "#271d30", "#fff0f7", mid=accent, midpoint=145
    ).convert("RGBA")
    emblem.putalpha(neutral.getchannel("A"))
    return emblem


@lru_cache(maxsize=4)
def _convergence_band(left_palette, right_palette):
    stops = [
        _rgb(left_palette[0]),
        _rgb(left_palette[2]),
        _mix(_rgb(left_palette[1]), _rgb(right_palette[1]), 0.5),
        _rgb(right_palette[2]),
        _rgb(right_palette[3]),
    ]
    band = Image.new("RGB", (1340, 1))
    colors = []
    for x in range(1340):
        t = x / 1339 * 4
        index = min(3, int(t))
        colors.append(_mix(stops[index], stops[index + 1], t - index))
    band.putdata(colors)
    return band.resize((1340, 44)).convert("RGBA")


def _convergence(image, left, right, left_accent, right_accent):
    draw = ImageDraw.Draw(image)
    common = _hex(_mix(_rgb(left_accent), _rgb(right_accent), 0.5))
    draw.rounded_rectangle((74, 692, 1526, 813), radius=42, fill="#130f19", outline=common, width=2)
    band = _convergence_band(tuple(left.palette), tuple(right.palette))
    mask = Image.new("L", band.size)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, 1339, 43), radius=22, fill=255)
    image.paste(band, (130, 739), mask)
    # Fine crossing light threads retain both profile palettes in the blend.
    threads = Image.new("RGBA", SIZE)
    td = ImageDraw.Draw(threads)
    for phase, color in ((0, left_accent), (math.pi, right_accent), (1.2, "#fff0f7")):
        points = [
            (130 + x, 761 + math.sin(x / 1340 * math.tau * 1.7 + phase) * 19)
            for x in range(0, 1341, 5)
        ]
        td.line(points, fill=(*_rgb(color), 155), width=1)
    image.alpha_composite(threads)


def render_duo(left, right, *, score, verdict, reason):
    left_accent, left_secondary = theme(left.palette)
    right_accent, right_secondary = theme(right.palette)
    common = _hex(_mix(_rgb(left_accent), _rgb(right_accent), 0.5))
    image = Image.new("RGBA", SIZE, "#100e17")
    glow = Image.new("RGBA", (400, 225))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-70, 15, 175, 245), fill=(*_rgb(left_accent), 30))
    gd.ellipse((225, 15, 470, 245), fill=(*_rgb(right_accent), 30))
    image.alpha_composite(
        glow.filter(ImageFilter.GaussianBlur(24)).resize(SIZE, Image.Resampling.BILINEAR)
    )
    _portrait(image, left, LEFT_X, left_accent, False)
    _portrait(image, right, RIGHT_X, right_accent, True)
    _convergence(image, left, right, left_accent, right_accent)
    image.alpha_composite(_side_ornaments(left_accent, left_secondary))
    image.alpha_composite(ImageOps.mirror(_side_ornaments(right_accent, right_secondary)), (800, 0))
    _identity(image, left, LEFT_X, left_accent)
    _identity(image, right, RIGHT_X, right_accent)
    image.alpha_composite(_sync_emblem(left_accent, right_accent), (700, 0))
    draw = ImageDraw.Draw(image)
    _spark(draw, 256, 46, 15, left_accent)
    draw.text((296, 22), "DUO", font=_serif(38), fill=left_accent)
    draw.text((399, 22), "STYLE", font=_serif(38), fill="#fff0f7")
    draw.text(
        (298, 67),
        "D I F F E R E N T  P A L E T T E S ,  S A M E  S T O R Y .",
        font=font(10),
        fill="#d4b7cd",
    )
    draw.text((1361, 31), "M E Y A Y A", font=font(13), anchor="ra", fill="#e2bfd8")
    _spark(draw, 1374, 39, 4, common)
    draw.text((1361, 53), "STYLE ANALYSIS", font=font(10), anchor="ra", fill="#bda7c1")
    draw.text((800, 277), "S T Y L E  S Y N C", font=_serif(17), anchor="ma", fill="#f1d7e9")
    draw.text((800, 299), f"{score}%", font=_score_font(), anchor="ma", fill="#fff0f7")
    draw.rounded_rectangle((665, 428, 935, 442), radius=7, fill="#503c58")
    if score > 0:
        draw.rounded_rectangle(
            (665, 428, 665 + max(14, 270 * score / 100), 442), radius=7, fill=common
        )
    _spark(draw, 665 + 270 * score / 100, 435, 9, "#fff1f7")
    draw.rounded_rectangle((674, 466, 926, 532), radius=18, fill="#17121d", outline="#69516d")
    _centred(draw, verdict, 800, 482, 230, 19, "#f3e4ef", lines=2)
    draw.line((697, 560, 903, 560), fill="#956780")
    _spark(draw, 800, 560, 9, common)
    _centred(draw, reason, 800, 590, 282, 19, "#dfcfdf", lines=3)
    # Paint labels last so neither palette-specific ornament can obscure them.
    draw.rounded_rectangle((608, 698, 992, 731), radius=10, fill="#15101b")
    draw.text(
        (800, 708), "C O L O R  C O N V E R G E N C E", font=font(13), anchor="ma", fill="#edbdd8"
    )
    _centred(draw, left.name.upper(), 240, 708, 240, 12, left_accent)
    _centred(draw, right.name.upper(), 1360, 708, 240, 12, right_accent)
    _spark(draw, 800, 760, 15, "#fff1f7")
    draw.line((270, 867, 1328, 867), fill="#6d4b66")
    draw.rounded_rectangle((652, 849, 948, 884), radius=8, fill="#100e17")
    draw.text(
        (800, 863),
        "M E Y A Y A  /  D U O  A N A L Y S I S",
        font=font(10),
        anchor="ma",
        fill="#c3a3ba",
    )
    draw.text(
        (1547, 863),
        "T W O  S T Y L E S ,  O N E  V I B E .",
        font=font(10),
        anchor="ra",
        fill="#ad92aa",
    )
    return image
