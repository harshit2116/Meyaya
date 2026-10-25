"""The Love Letter layout; scoring remains owned by ShipService."""

from functools import lru_cache
from io import BytesIO
import math
from pathlib import Path
import unicodedata

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

from bot.services.aura_archive import _asset, _serif, _spark, _text
from bot.services.card_renderer import font
from bot.services.duostyle_archive import _centred, _mix

SIZE = (1600, 866)
PORTRAIT_SIZE = 328
CENTERS = (375, 1225)
PORTRAIT_Y = 180
PINK, BLUE = "#f196b6", "#a4b9f6"


def ship_breakdown(percentage):
    """Playful display derivatives, not additional relationship measurements."""
    p = max(0, min(100, int(percentage)))
    return {"chemistry": min(100, p + 4), "chaos": min(100, 139 - p), "harmony": max(0, p - 2)}


def ship_description(percentage):
    if percentage >= 95:
        return "Even the stars are taking notes. This pairing has main-character energy."
    if percentage >= 85:
        return "The sparks are impossible to ignore. Meyaya is already choosing the soundtrack."
    if percentage >= 70:
        return "You two have a surprisingly strong balance. Different energies, but they flow well together."
    if percentage >= 50:
        return "There is something here. A little curiosity, a little courage, and maybe a very good first chapter."
    if percentage >= 30:
        return (
            "The chemistry is still finding its rhythm. The chaos, however, arrived right on time."
        )
    if percentage >= 10:
        return "A bold pairing with a complicated plot. Meyaya recommends a conversation before the wedding plans."
    return "The universe may need another draft. There is always room for a good friendship arc."


def _clean(value):
    return "".join(c for c in value if unicodedata.category(c) not in {"So", "Mn", "Cf"}).strip()


def _flower(draw, x, y, r, color):
    for i in range(5):
        a = i * math.tau / 5
        cx, cy = x + math.sin(a) * r * 0.55, y + math.cos(a) * r * 0.55
        draw.ellipse((cx - r * 0.33, cy - r * 0.33, cx + r * 0.33, cy + r * 0.33), fill=color)
    draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill="#342438")


@lru_cache(maxsize=1)
def _emblem():
    path = Path(__file__).resolve().parents[1] / "assets/celestial/ship/linked-hearts.png"
    with Image.open(path) as art:
        return ImageOps.contain(art.convert("RGBA"), (300, 200), Image.Resampling.LANCZOS)


@lru_cache(maxsize=1)
def _score_font():
    for path in (
        "C:/Windows/Fonts/georgiai.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
    ):
        if Path(path).is_file():
            return ImageFont.truetype(path, 108)
    return _serif(108)


@lru_cache(maxsize=1)
def _base():
    image = Image.new("RGBA", SIZE, "#15121b")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (28, 30, 1572, 832), radius=26, fill="#121017", outline="#a1809b", width=2
    )
    _flower(draw, 89, 91, 25, PINK)
    draw.text((143, 64), "MEYAYA / THE LOVE LETTER", font=font(29), fill="#fae7f2")
    draw.text((144, 105), "A LITTLE CHEMISTRY, A LITTLE CHAOS", font=font(17), fill="#bc9fb5")
    draw.line((602, 79, 799, 79), fill="#936a84")
    _spark(draw, 585, 79, 9, "#86667d")
    _spark(draw, 800, 137, 19, PINK)
    draw.text((1501, 72), "M E Y A Y A", font=font(17), anchor="ra", fill=BLUE)
    draw.text((1501, 101), "SHIP ANALYSIS", font=font(13), anchor="ra", fill="#c9adc8")
    _spark(draw, 1531, 79, 11, PINK)
    draw.rounded_rectangle(
        (52, 577, 1548, 799), radius=24, fill="#201923", outline="#97788f", width=2
    )
    _spark(draw, 98, 615, 19, PINK)
    draw.text((143, 606), "S H I P  R E S U L T", font=font(19), fill=PINK)
    draw.line((98, 653, 98, 772), fill=PINK, width=2)
    draw.line((960, 607, 960, 772), fill="#75576f")
    return image


@lru_cache(maxsize=1)
def _portrait_mask():
    size = PORTRAIT_SIZE
    mask = Image.new("L", (size * 3, size * 3))
    ImageDraw.Draw(mask).ellipse((0, 0, size * 3 - 1, size * 3 - 1), fill=255)
    return mask.resize((size, size), Image.Resampling.LANCZOS)


@lru_cache(maxsize=1)
def _panel_mask():
    mask = Image.new("L", (500, 245))
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, 499, 244), radius=18, fill=170)
    # A soft irregular feather makes the panel feel painted, while all geometry
    # is reusable and contains no member image data.
    fade = Image.new("L", (500, 1))
    fade.putdata([round(255 * min(1, max(0, (500 - x) / 80))) for x in range(500)])
    return ImageChops.multiply(mask, fade.resize(mask.size))


def _portrait(image, data, name, cx, color, mirrored=False):
    art = _asset(data)
    if art is None:
        art = Image.new("RGBA", (328, 328), "#292030")
        ImageDraw.Draw(art).text(
            (164, 164), name[:1] or "?", font=_serif(100), anchor="mm", fill=color
        )
    # Portrait-derived panels keep the look of the reference without two extra
    # Discord profile lookups or banner downloads on each ship roll.
    panel = ImageOps.fit(art, (500, 245), Image.Resampling.LANCZOS).filter(
        ImageFilter.GaussianBlur(4)
    )
    wash = Image.new("RGBA", panel.size, color)
    panel = Image.blend(panel.convert("RGBA"), wash, 0.45)
    x = 100 if not mirrored else 1000
    mask = ImageOps.mirror(_panel_mask()) if mirrored else _panel_mask()
    draw = ImageDraw.Draw(image)
    # Orbit marks and small rounded side tiles reproduce the framing rhythm.
    side = 60 if not mirrored else 1450
    draw.rounded_rectangle(
        (side, 177, side + 90, 294), radius=15, fill="#322334" if not mirrored else "#252b43"
    )
    draw.rounded_rectangle(
        (side, 425, side + 80, 500), radius=14, fill="#322334" if not mirrored else "#252b43"
    )
    _spark(draw, side + 20 if not mirrored else side + 60, 215, 14, color)
    for i in range(4):
        px = side + 15 if not mirrored else side + 65
        draw.ellipse((px - 3, 329 + i * 18, px + 3, 335 + i * 18), fill=color)
    image.paste(panel, (x, 212), mask)
    draw = ImageDraw.Draw(image)
    for pad, width in ((12, 2), (3, 2)):
        draw.ellipse(
            (cx - 164 - pad, 180 - pad, cx + 164 + pad, 508 + pad),
            outline=("#fff0f7" if pad == 3 else color),
            width=width,
        )
    for degree in range(196, 333, 4):
        angle = math.radians(degree)
        px, py = cx + 194 * math.cos(angle), 342 + 194 * math.sin(angle)
        draw.ellipse((px - 1, py - 1, px + 1, py + 1), fill="#82667d")
    portrait = ImageOps.fit(art, (328, 328), Image.Resampling.LANCZOS)
    flattened = Image.new("RGBA", portrait.size, "#291e31")
    flattened.alpha_composite(portrait)
    image.paste(flattened, (cx - 164, PORTRAIT_Y), _portrait_mask())
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (cx - 171, 482, cx + 171, 543),
        radius=29,
        fill="#30222f" if not mirrored else "#25283a",
        outline=color,
        width=2,
    )
    _centred(draw, name, cx, 491, 310, 38, "#fff0f7", serif=True)
    bx = cx - 145 if not mirrored else cx + 145
    draw.ellipse((bx - 26, 429, bx + 26, 481), fill="#241e2a", outline=color, width=2)
    _flower(draw, bx, 455, 20, color)


def _metric_icon(draw, x, y, kind, color):
    if kind == "chemistry":
        points = []
        for i in range(81):
            t = i * math.tau / 80
            points.append(
                (
                    x + math.sin(t) ** 3 * 13,
                    y
                    - (
                        13 * math.cos(t)
                        - 5 * math.cos(2 * t)
                        - 2 * math.cos(3 * t)
                        - math.cos(4 * t)
                    )
                    * 0.8,
                )
            )
        draw.line(points, fill=color, width=2)
    elif kind == "chaos":
        draw.text((x, y - 1), "∞", font=font(37), anchor="mm", fill=color)
    else:
        draw.ellipse((x - 14, y - 13, x - 2, y - 1), outline=color, width=2)
        draw.ellipse((x + 3, y - 10, x + 13, y), outline=color, width=2)
        draw.arc((x - 19, y - 1, x + 3, y + 18), 180, 360, fill=color, width=2)
        draw.arc((x, y + 2, x + 18, y + 18), 180, 360, fill=color, width=2)


def render_letter(first, second, name_one, name_two, percentage, verdict):
    percentage = max(0, min(100, int(percentage)))
    image = _base().copy()
    _portrait(image, first, name_one, CENTERS[0], PINK)
    _portrait(image, second, name_two, CENTERS[1], BLUE, True)
    image.alpha_composite(_emblem(), (650, 163))
    draw = ImageDraw.Draw(image)
    draw.text((800, 333), f"{percentage}%", font=_score_font(), anchor="ma", fill="#fff0f7")
    draw.text((800, 451), "C O M P A T I B I L I T Y", font=font(18), anchor="ma", fill="#cfacc7")
    draw.rounded_rectangle((635, 488, 965, 508), radius=10, fill="#342b35", outline="#6d5669")
    if percentage:
        width = max(20, round(328 * percentage / 100))
        gradient = Image.new("RGB", (width, 1))
        gradient.putdata(
            [_mix((249, 145, 185), (166, 173, 244), x / max(1, width - 1)) for x in range(width)]
        )
        gradient = gradient.resize((width, 18))
        mask = Image.new("L", gradient.size)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, width - 1, 17), radius=9, fill=255)
        image.paste(gradient, (636, 489), mask)
    draw = ImageDraw.Draw(image)
    _text(draw, (143, 645, 760, 60), _clean(verdict), 41, "#f9edf6", minimum=25)
    _text(
        draw,
        (143, 709, 755, 68),
        ship_description(percentage),
        25,
        "#baa0b7",
        minimum=20,
        serif=False,
    )
    for index, (kind, color) in enumerate(
        (("chemistry", "#f28eb7"), ("chaos", "#d78ded"), ("harmony", BLUE))
    ):
        value = ship_breakdown(percentage)[kind]
        y = 636 + index * 55
        _metric_icon(draw, 1015, y, kind, color)
        draw.text((1056, y - 11), kind.upper(), font=font(18), fill="#f3e5f2")
        draw.rounded_rectangle(
            (1182, y - 8, 1458, y + 9), radius=9, fill="#342c39", outline="#47374a"
        )
        if value:
            draw.rounded_rectangle(
                (1182, y - 8, 1182 + max(17, 276 * value / 100), y + 9), radius=9, fill=color
            )
        draw.text((1508, y - 10), str(value), font=font(20), anchor="ra", fill="#fff0f7")
    output = BytesIO()
    image.convert("RGB").save(output, "PNG", compress_level=3)
    return output.getvalue()
