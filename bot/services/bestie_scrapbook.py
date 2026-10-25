"""Pair-specific scrapbook cards using a fixed, photo-free illustrated template."""

from functools import lru_cache
from io import BytesIO
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from bot.services.aura_archive import _asset, _serif, _text
from bot.services.card_renderer import font

SIZE = (1672, 941)
ASSETS = Path(__file__).resolve().parents[1] / "assets/celestial/besties"
INK = "#302a35"


@lru_cache(maxsize=1)
def _template():
    # All four photo windows are transparent. No reference member photos,
    # names, scores, verdicts or filled bars are present in this shared asset.
    with Image.open(ASSETS / "scrapbook-template.png") as source:
        return source.convert("RGBA").resize(SIZE, Image.Resampling.LANCZOS)


@lru_cache(maxsize=32)
def _hand(size, bold=False):
    path = ASSETS / ("Kalam-Bold.ttf" if bold else "Caveat.ttf")
    return ImageFont.truetype(path, size)


def bestie_breakdown(score):
    """Playful display variations from the existing daily score, not new rolls."""
    p = max(0, min(100, int(score)))
    return {
        "conversation": min(100, p + 5),
        "chaos_sync": min(100, p + 1),
        "hangout_potential": min(100, p + 7),
    }


def _paper_note(score):
    if score >= 80:
        return ("Same wavelength, matching chaos.", "The group chat never stood a chance.")
    if score >= 60:
        return ("Good company, excellent side quests.", "Keep the shared chaos going.")
    if score >= 40:
        return ("A friendship still finding its rhythm.", "Start with snacks and a good story.")
    return ("Different wavelengths...", "but that's what makes it interesting.")


def _report(verdict):
    # Reflow the existing verdict; do not replace it with an unrelated report.
    for separator in (". ", " - ", ", but "):
        if separator in verdict:
            first, second = verdict.split(separator, 1)
            if separator == ", but ":
                first += "."
            elif separator == ". ":
                first += "."
            second = second[:1].upper() + second[1:]
            return first, second
    return verdict, ""


def _avatar(data, name):
    art = _asset(data)
    if art is None:
        art = Image.new("RGBA", (400, 400), "#4a3b50")
        ImageDraw.Draw(art).text(
            (200, 200), name[:1] or "?", font=_serif(120), anchor="mm", fill="#f6d9e5"
        )
    result = Image.new("RGBA", art.size, "#302836")
    result.alpha_composite(art)
    return result


def _photo(image, art, size, angle, position, *, film=False):
    photo = ImageOps.fit(art, size, method=Image.Resampling.LANCZOS)
    if film:
        photo = ImageOps.colorize(ImageOps.grayscale(photo), "#251d2a", "#d5a6bd").convert("RGBA")
    photo = photo.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    image.alpha_composite(photo, position)


def _hand_line(image, value, center, size, width, angle=0, color=INK, heart=False):
    value = " ".join(str(value).split())[:100]
    canvas = Image.new("RGBA", (width, 76))
    draw = ImageDraw.Draw(canvas)
    chosen = _hand(size)
    # General Unicode fonts keep unsupported display names safe without
    # changing the bundled handwritten look for Latin-script names.
    if any(ord(c) > 0x2FFF for c in value):
        chosen = font(size)
    while size > 18 and draw.textlength(value, font=chosen) > width - (48 if heart else 12):
        size -= 1
        chosen = font(size) if any(ord(c) > 0x2FFF for c in value) else _hand(size)
    while len(value) > 1 and draw.textlength(value, font=chosen) > width - (48 if heart else 12):
        value = value[:-2] + "…"
    name_center = width / 2 - (14 if heart else 0)
    draw.text((name_center, 38), value, font=chosen, fill=color, anchor="mm")
    if heart:
        text_width = draw.textlength(value, font=chosen)
        hx = name_center + text_width / 2 + 21
        points = []
        for step in range(81):
            t = step * math.tau / 80
            points.append(
                (
                    hx + math.sin(t) ** 3 * 11,
                    36
                    - (
                        13 * math.cos(t)
                        - 5 * math.cos(2 * t)
                        - 2 * math.cos(3 * t)
                        - math.cos(4 * t)
                    )
                    * 0.7,
                )
            )
        draw.line(points, fill=color, width=2)
        draw.line(
            (name_center - text_width / 2, 59, name_center + text_width / 2, 58),
            fill="#d791b0",
            width=1,
        )
    canvas = canvas.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    image.alpha_composite(
        canvas, (round(center[0] - canvas.width / 2), round(center[1] - canvas.height / 2))
    )


def _score(image, score):
    canvas = Image.new("RGBA", (398, 148))
    draw = ImageDraw.Draw(canvas)
    text = f"{score}%"
    size = 128
    while size > 80 and draw.textlength(text, font=_hand(size, True)) > 345:
        size -= 1
    chosen = _hand(size, True)
    draw.text(
        (204, 76),
        text,
        font=chosen,
        anchor="mm",
        fill="#d785a4",
        stroke_width=2,
        stroke_fill="#d785a4",
    )
    draw.text((199, 72), text, font=chosen, anchor="mm", fill=INK)
    canvas = canvas.rotate(3.3, resample=Image.Resampling.BICUBIC, expand=True)
    image.alpha_composite(canvas, (round(844 - canvas.width / 2), round(379 - canvas.height / 2)))
    # Fill only the interiors of the ten existing notebook meter segments.
    fill = Image.new("RGBA", (330, 22))
    fd = ImageDraw.Draw(fill)
    remaining = 330 * score / 100
    for i in range(10):
        start = i * 33 + 2
        end = min(start + 29, remaining)
        if end > start:
            fd.rounded_rectangle(
                (start, 3, end, 18), radius=min(7, (end - start) / 2), fill="#e9b5d4"
            )
    fill = fill.rotate(3.3, resample=Image.Resampling.BICUBIC, expand=True)
    image.alpha_composite(fill, (680, 441))


def render_scrapbook(first, second, name_one, name_two, score, verdict):
    score = max(0, min(100, int(score)))
    left, right = _avatar(first, name_one), _avatar(second, name_two)
    image = Image.new("RGBA", SIZE, "#19151e")
    # These angles map the reference's four transparent photographic windows.
    _photo(image, left, (240, 185), 9.3, (-32, 410), film=True)
    _photo(image, right, (260, 190), -10, (1477, 387), film=True)
    _photo(image, left, (400, 365), 9.3, (165, 130))
    _photo(image, right, (391, 373), -9.8, (1067, 130))
    image.alpha_composite(_template())
    _hand_line(image, name_one, (416, 548), 43, 260, 9.3, heart=True)
    _hand_line(image, name_two, (1197, 537), 43, 260, -9.8, color="#8a597d", heart=True)
    _score(image, score)
    note_one, note_two = _paper_note(score)
    _hand_line(image, note_one, (833, 509), 27, 345, 3.3)
    _hand_line(image, note_two, (849, 535), 27, 360, 3.3)
    title, subtitle = _report(verdict)
    draw = ImageDraw.Draw(image)
    _text(draw, (178, 700, 690, 66), title, 43, "#fbecf2", minimum=26)
    if subtitle:
        _text(draw, (178, 772, 680, 52), subtitle, 30, "#bda5bc", minimum=20)
    values = bestie_breakdown(score)
    for index, key in enumerate(("conversation", "chaos_sync", "hangout_potential")):
        value = values[key]
        y = 680 + index * 54
        if value:
            draw.rounded_rectangle(
                (1268, y, 1268 + 218 * value / 100, y + 19),
                radius=9,
                fill="#edb4ce" if index < 2 else "#c7b4ee",
                outline="#66536d",
            )
        draw.text((1524, y + 10), str(value), font=font(25), anchor="mm", fill="#272532")
    output = BytesIO()
    image.convert("RGB").save(output, "PNG", compress_level=3)
    return output.getvalue()
