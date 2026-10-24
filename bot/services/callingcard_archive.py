"""Palette-driven calling cards; all member content is composed locally."""

from functools import lru_cache
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from bot.services.aura_archive import _asset, _serif, _text
from bot.services.card_renderer import font
from bot.services.duostyle_archive import _hex, _mix, _rgb, theme

SIZE = (1600, 900)
AVATAR = (150, 157, 480)


def _flower(draw, x, y, radius, color):
    for i in range(5):
        angle = i * math.tau / 5
        cx, cy = x + math.sin(angle) * radius * 0.6, y + math.cos(angle) * radius * 0.6
        r = radius * 0.38
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill="#3c2934")


@lru_cache(maxsize=1)
def _frame_source():
    path = Path(__file__).resolve().parents[1] / "assets/profile/callingcard/portrait-frame.png"
    with Image.open(path) as art:
        frame = art.convert("RGBA").resize((640, 640), Image.Resampling.LANCZOS)
    return ImageOps.grayscale(frame), frame.getchannel("A")


@lru_cache(maxsize=4)
def _portrait_frame(accent, secondary):
    gray, alpha = _frame_source()
    layer = ImageOps.colorize(
        gray,
        _hex(_mix(_rgb(secondary), (30, 18, 28), 0.5)),
        _hex(_mix(_rgb(accent), (255, 243, 230), 0.6)),
        mid=accent,
        midpoint=140,
    ).convert("RGBA")
    layer.putalpha(alpha)
    return layer


@lru_cache(maxsize=3)
def _background(palette):
    """Only three member-free backgrounds; callers always receive a copy."""
    accent, secondary = theme(palette)
    base = _hex(_mix(_rgb(palette[3]), (12, 10, 16), 0.96))
    image = Image.new("RGBA", SIZE, base)
    # Low-resolution gradients avoid blurring full-size buffers per request.
    glow = Image.new("RGBA", (400, 225))
    draw = ImageDraw.Draw(glow)
    draw.ellipse((-140, -70, 180, 275), fill=(*_rgb(accent), 22))
    draw.ellipse((210, 135, 520, 360), fill=(*_rgb(secondary), 24))
    image.alpha_composite(
        glow.filter(ImageFilter.GaussianBlur(40)).resize(SIZE, Image.Resampling.BILINEAR)
    )
    draw = ImageDraw.Draw(image)
    border = _hex(_mix(_rgb(accent), (255, 226, 209), 0.35))
    draw.rounded_rectangle((35, 50, 1565, 855), radius=40, outline=border, width=3)
    draw.text((94, 80), "M E Y A Y A  ·  C A L L I N G  C A R D", font=_serif(22), fill=accent)
    draw.line((514, 95, 594, 95), fill=accent, width=1)
    _flower(draw, 607, 95, 8, accent)
    draw.line((111, 164, 111, 623), fill=accent, width=1)
    for y in (215, 369, 572):
        _flower(draw, 111, y, 11, accent)
    draw.text((94, 665), "S I G N A T U R E   C O L O R S", font=_serif(19), fill=accent)
    draw.line((415, 675, 1510, 675), fill=_hex(_mix(_rgb(accent), _rgb(base), 0.48)), width=1)
    for index, color in enumerate(palette[:5]):
        x = 94 + index * 170
        draw.rounded_rectangle((x, 704, x + 155, 774), radius=17, fill=color)
    _flower(draw, 96, 816, 17, accent)
    _flower(draw, 1507, 816, 15, accent)
    draw.line((127, 816, 708, 816), fill=accent, width=1)
    _text(
        draw,
        (730, 804, 750, 32),
        "A living card shaped by their Discord style and bond with Meyaya.",
        20,
        _hex(_mix(_rgb(accent), (190, 174, 188), 0.6)),
        minimum=15,
    )
    return image


@lru_cache(maxsize=1)
def _avatar_mask():
    mask = Image.new("L", (AVATAR[2], AVATAR[2]))
    ImageDraw.Draw(mask).ellipse((0, 0, AVATAR[2] - 1, AVATAR[2] - 1), fill=255)
    return mask


def _portrait(image, visual, accent, secondary):
    x, y, size = AVATAR
    art = _asset(visual.avatar)
    if art is None:
        art = Image.new("RGBA", (size, size), visual.palette[3])
        ImageDraw.Draw(art).text(
            (size / 2, size / 2), visual.name[:1] or "?", font=_serif(130), anchor="mm", fill=accent
        )
    art = ImageOps.fit(art, (size, size), method=Image.Resampling.LANCZOS)
    image.paste(art, (x, y), _avatar_mask())
    image.alpha_composite(_portrait_frame(accent, secondary), (75, 92))
    # Equipped decoration remains intact above the decorative card frame.
    decoration = _asset(visual.decoration)
    if decoration is not None:
        decoration = ImageOps.contain(decoration, (540, 540), Image.Resampling.LANCZOS)
        image.alpha_composite(
            decoration, (x + (size - decoration.width) // 2, y + (size - decoration.height) // 2)
        )


def _clean_title(value):
    value = " ".join(str(value).split())
    return value[next((i for i, char in enumerate(value) if char.isalnum()), len(value)) :][:100]


@lru_cache(maxsize=32)
def _icon(kind, color):
    layer = Image.new("RGBA", (120, 120))
    draw = ImageDraw.Draw(layer)
    if kind == "crown":
        draw.polygon(
            ((15, 40), (38, 58), (60, 21), (82, 58), (105, 40), (94, 88), (26, 88)), fill=color
        )
        draw.rounded_rectangle((25, 94, 95, 103), radius=3, fill=color)
    elif kind == "people":
        draw.ellipse((21, 23, 59, 61), fill=color)
        draw.ellipse((68, 33, 96, 61), fill=color)
        draw.rounded_rectangle((10, 68, 72, 102), radius=16, fill=color)
        draw.rounded_rectangle((75, 68, 108, 102), radius=13, fill=color)
    elif kind == "heart":
        points = []
        for i in range(121):
            t = i * math.tau / 120
            points.append(
                (
                    60 + 2.9 * 16 * math.sin(t) ** 3,
                    56
                    - 2.9
                    * (
                        13 * math.cos(t)
                        - 5 * math.cos(2 * t)
                        - 2 * math.cos(3 * t)
                        - math.cos(4 * t)
                    ),
                )
            )
        draw.polygon(points, fill=color)
    else:
        points = []
        for i in range(10):
            a = i * math.pi / 5 - math.pi / 2
            r = 49 if i % 2 == 0 else 22
            points.append((60 + math.cos(a) * r, 61 + math.sin(a) * r))
        draw.polygon(points, fill=color)
    return layer.resize((40, 40), Image.Resampling.LANCZOS)


def _badges(image, titles, accent, secondary):
    titles = tuple(filter(None, (_clean_title(title) for title in titles)))
    if not titles:
        titles = ("New Face",)
    # Normal profiles supply at most three titles. Wrap additional callers'
    # titles inside this fixed region rather than silently dropping them.
    columns = min(3, len(titles))
    rows = math.ceil(len(titles) / columns)
    height = min(68, 106 / rows - 8)
    width = (810 - (columns - 1) * 14) / columns
    for index, title in enumerate(titles):
        x, y = round(710 + (index % columns) * (width + 14)), round(
            548 + (index // columns) * (height + 8)
        )
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle(
            (x, y, x + width, y + height),
            radius=18,
            fill=_hex(_mix(_rgb(secondary), (28, 17, 30), 0.67)),
            outline=accent,
            width=2,
        )
        lowered = title.lower()
        kind = "crown" if "parent" in lowered else "people" if "circle" in lowered else "star"
        icon_size = min(36, round(height - 14))
        icon = _icon(kind, accent).resize((icon_size, icon_size), Image.Resampling.LANCZOS)
        image.alpha_composite(icon, (x + 16, round(y + (height - icon_size) / 2)))
        _text(
            ImageDraw.Draw(image),
            (x + 62, y + 13, round(width - 74), round(height - 18)),
            title,
            25,
            "#faedf2",
            minimum=14,
        )


def render_callingcard(visual, *, nickname, relationship, titles):
    accent, secondary = theme(visual.palette)
    image = _background(tuple(visual.palette)).copy()
    _portrait(image, visual, accent, secondary)
    draw = ImageDraw.Draw(image)
    _text(draw, (710, 172, 808, 144), visual.name, 124, "#fff0f0", minimum=32)
    draw.line((710, 317, 882, 317), fill=accent, width=2)
    _flower(draw, 898, 317, 9, accent)
    _text(
        draw,
        (710, 339, 810, 88),
        f"“{nickname}”" if nickname else "Nickname still loading...",
        46,
        accent,
        minimum=23,
    )
    image.alpha_composite(_icon("heart", accent), (710, 431))
    draw = ImageDraw.Draw(image)
    draw.text((760, 442), "M E Y A Y A ’ S   B O N D", font=_serif(21), fill=accent)
    draw.line((1010, 451, 1510, 451), fill=_hex(_mix(_rgb(accent), (25, 17, 28), 0.5)), width=1)
    bond = " ".join(str(relationship).split()) or "Still getting to know them"
    bond = bond[0].upper() + bond[1:]
    if bond[-1] not in ".!?":
        bond += "."
    _text(draw, (710, 482, 810, 58), bond, 35, "#fff0f0", minimum=19)
    _badges(image, titles, accent, secondary)
    return image
