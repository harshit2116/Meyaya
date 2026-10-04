"""Meyaya's Soul Interface: portrait crest, affinity glyphs and a local ritual."""

from io import BytesIO
import math

from PIL import Image, ImageDraw, ImageOps

from bot.data.fantasy import AFFINITIES, CLASSES, RARITIES, RARITY_COLORS
from bot.services.card_renderer import font

CARD_SIZE = (900, 1000)
MAX_CARD_BYTES = 4 * 1024 * 1024


def theme_for(profile):
    return AFFINITIES.get(profile.affinity_id, AFFINITIES["arcane"])


def rgb(color):
    return tuple(bytes.fromhex(color.lstrip("#")))


def blend(a, b, amount):
    return tuple(round(x + (y - x) * amount) for x, y in zip(a, b))


def flower(draw, x, y, radius, color):
    for angle in range(0, 360, 72):
        theta = math.radians(angle)
        cx, cy = x + math.sin(theta) * radius * 0.65, y + math.cos(theta) * radius * 0.65
        r = radius * 0.48
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=2)
    draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=color)


def glyph(draw, center, radius, kind, color, width=3):
    x, y = center
    if kind in {"star", "sun", "rune"}:
        count = 8 if kind == "sun" else 4 if kind == "star" else 6
        points = []
        for i in range(count * 2):
            angle = -math.pi / 2 + i * math.pi / count
            r = radius if i % 2 == 0 else radius * 0.35
            points.append((x + math.cos(angle) * r, y + math.sin(angle) * r))
        draw.polygon(points, outline=color, width=width)
        if kind == "rune":
            draw.ellipse(
                (x - radius * 0.6, y - radius * 0.6, x + radius * 0.6, y + radius * 0.6),
                outline=color,
                width=width,
            )
    elif kind == "moon":
        draw.arc((x - radius, y - radius, x + radius, y + radius), 45, 315, fill=color, width=width)
        draw.arc(
            (x - radius * 0.35, y - radius, x + radius * 1.35, y + radius),
            100,
            260,
            fill=color,
            width=width,
        )
    elif kind == "bolt":
        draw.line(
            (
                (x + radius * 0.5, y - radius),
                (x - radius * 0.6, y + radius * 0.1),
                (x + radius * 0.2, y + radius * 0.1),
                (x - radius * 0.4, y + radius),
            ),
            fill=color,
            width=width,
        )
    elif kind in {"crystal", "rift"}:
        draw.polygon(
            ((x, y - radius), (x + radius * 0.7, y), (x, y + radius), (x - radius * 0.7, y)),
            outline=color,
            width=width,
        )
        draw.line((x, y - radius, x, y + radius), fill=color, width=width)
        if kind == "rift":
            draw.arc(
                (x - radius * 1.2, y - radius * 0.5, x + radius * 1.2, y + radius * 0.5),
                190,
                350,
                fill=color,
                width=width,
            )
    elif kind == "wave":
        points = [
            (x - radius + i * radius / 12, y + math.sin(i / 24 * math.pi * 2) * radius * 0.25)
            for i in range(25)
        ]
        draw.line(points, fill=color, width=width)
        draw.line([(a, b + radius * 0.4) for a, b in points], fill=color, width=width)
    elif kind == "leaf":
        draw.ellipse(
            (x - radius * 0.5, y - radius, x + radius * 0.5, y + radius), outline=color, width=width
        )
        draw.line((x, y - radius, x, y + radius), fill=color, width=width)
    elif kind == "flame":
        draw.line(
            (
                (x, y - radius),
                (x - radius * 0.8, y + radius * 0.35),
                (x, y + radius),
                (x + radius * 0.8, y + radius * 0.35),
                (x, y - radius),
            ),
            fill=color,
            width=width,
        )
        draw.line(
            ((x, y), (x - radius * 0.2, y + radius * 0.5), (x, y + radius * 0.8)),
            fill=color,
            width=width,
        )
    elif kind in {"blade", "arrow"}:
        draw.polygon(
            (
                (x, y - radius),
                (x + radius * 0.25, y + radius * 0.2),
                (x, y + radius * 0.4),
                (x - radius * 0.25, y + radius * 0.2),
            ),
            outline=color,
            width=width,
        )
        draw.line(
            (x - radius * 0.6, y + radius * 0.4, x + radius * 0.6, y + radius * 0.4),
            fill=color,
            width=width,
        )
        draw.line((x, y + radius * 0.4, x, y + radius), fill=color, width=width)
    else:
        draw.polygon(
            (
                (x - radius * 0.7, y - radius),
                (x + radius * 0.7, y - radius),
                (x + radius * 0.6, y + radius * 0.3),
                (x, y + radius),
                (x - radius * 0.6, y + radius * 0.3),
            ),
            outline=color,
            width=width,
        )


def portrait(data, name, size=260):
    art = Image.new("RGB", (size, size), "#2b233b")
    if data and len(data) <= 6 * 1024 * 1024:
        try:
            with Image.open(BytesIO(data)) as source:
                if source.width * source.height <= 4_000_000:
                    rgba = ImageOps.fit(
                        source.convert("RGBA"), art.size, method=Image.Resampling.LANCZOS
                    )
                    art.paste(rgba, (0, 0), rgba)
                    return art
        except (OSError, ValueError):
            pass
    ImageDraw.Draw(art).text(
        (size // 2, size // 2),
        str(name)[:1].upper() or "?",
        font=font(size // 3),
        fill="#f1dbef",
        anchor="mm",
    )
    return art


def centered(draw, y, text, size, color, width=760):
    text = " ".join(str(text).split())[:150]
    while size > 14 and draw.textlength(text, font=font(size)) > width:
        size -= 1
    if draw.textlength(text, font=font(size)) > width:
        while text and draw.textlength(text + "…", font=font(size)) > width:
            text = text[:-1]
        text += "…"
    draw.text((450, y), text, font=font(size), fill=color, anchor="mt")


def render_soul_card(profile, name, avatar=b""):
    theme = theme_for(profile)
    dark, accent = rgb(theme.dark), rgb(theme.color)
    image = Image.new("RGB", CARD_SIZE)
    d = ImageDraw.Draw(image)
    for y in range(1000):
        glow = max(0, 1 - abs(y - 345) / 700) * 0.17
        d.line((0, y, 900, y), fill=blend(dark, accent, glow))
    # Constellation geometry and an affinity-specific seal, drawn locally.
    for i in range(34):
        x, y = (i * 191 + profile.user_id % 73) % 860 + 20, (i * 137) % 930 + 30
        radius = 1 if i % 3 else 2
        d.ellipse((x - radius, y - radius, x + radius, y + radius), fill=blend(dark, accent, 0.55))
    d.rounded_rectangle((22, 22, 877, 977), radius=30, outline=blend(dark, accent, 0.5), width=2)
    d.rounded_rectangle((34, 34, 865, 965), radius=24, outline=blend(dark, accent, 0.20), width=1)
    flower(d, 450, 43, 13, theme.color)
    centered(d, 70, "M E Y A Y A   /   S O U L   I N T E R F A C E", 17, theme.color)
    centered(d, 108, name, 36, "#fff6fa")
    centered(d, 158, profile.fantasy_title, 23, "#ddcfe8")
    rarity_index = RARITIES.index(profile.weapon_rarity) if profile.weapon_rarity in RARITIES else 0
    rarity = RARITY_COLORS[rarity_index]
    for radius, color, width in (
        (180, blend(dark, accent, 0.25), 1),
        (158, theme.color, 2),
        (145, rarity, 2),
    ):
        d.ellipse(
            (450 - radius, 367 - radius, 450 + radius, 367 + radius), outline=color, width=width
        )
    for angle in range(0, 360, 45):
        theta = math.radians(angle)
        x, y = 450 + math.cos(theta) * 170, 367 + math.sin(theta) * 170
        d.polygon(((x, y - 4), (x + 4, y), (x, y + 4), (x - 4, y)), fill=theme.color)
    art = portrait(avatar, name)
    mask = Image.new("L", art.size)
    ImageDraw.Draw(mask).ellipse((0, 0, 259, 259), fill=255)
    image.paste(art, (320, 237), mask)
    # The flower marks the personal crest; the class emblem is a separate seal.
    d.ellipse((417, 477, 483, 543), fill=theme.dark, outline=theme.color, width=2)
    glyph(d, (450, 510), 22, CLASSES.get(profile.class_id, CLASSES["mage"]).emblem, theme.color, 2)
    centered(d, 556, profile.class_name.upper(), 46, "#fff6fa")
    centered(d, 615, profile.subclass_name, 26, "#ddcfe8")
    glyph(d, (332, 679), 17, theme.motif, theme.color, 2)
    d.text((365, 663), profile.affinity_name.upper() + " AFFINITY", font=font(24), fill=theme.color)
    d.line((130, 724, 390, 724), fill=blend(dark, accent, 0.5), width=1)
    flower(d, 450, 724, 12, theme.color)
    d.line((510, 724, 770, 724), fill=blend(dark, accent, 0.5), width=1)
    for y, title, current, total, color in (
        (762, "HP", profile.hp, profile.max_hp, theme.color),
        (828, "MP", profile.mp, profile.max_mp, "#c6b8ef"),
    ):
        d.text((100, y), title, font=font(23), fill="#ece2f2")
        d.text((800, y), f"{current} / {total}", font=font(23), fill="#ece2f2", anchor="ra")
        d.rounded_rectangle((166, y + 6, 640, y + 25), radius=9, fill=blend(dark, accent, 0.12))
        fill = 474 * max(0, min(1, current / max(1, total)))
        if fill:
            d.rounded_rectangle((166, y + 6, 166 + max(18, fill), y + 25), radius=9, fill=color)
    centered(
        d, 902, f"LEVEL {profile.level:02d}  ·  {profile.xp} XP  ·  SOULBOUND", 20, theme.color
    )
    centered(d, 939, theme.lore, 17, "#b9acc8")
    output = BytesIO()
    image.save(output, "PNG")
    data = output.getvalue()
    if len(data) > MAX_CARD_BYTES:
        raise ValueError("Soul card exceeds upload budget")
    return data


def render_ritual(profile):
    """One compact, non-flashing sigil animation for first awakening only."""
    theme = theme_for(profile)
    base = Image.new("RGB", (560, 280), theme.dark)
    sample = base.copy()
    sd = ImageDraw.Draw(sample)
    sd.rectangle((0, 0, 100, 40), fill=theme.color)
    sd.rectangle((110, 0, 210, 40), fill="#f7eefb")
    palette = sample.quantize(colors=128)
    frames = []
    for i in range(24):
        image = base.copy()
        d = ImageDraw.Draw(image)
        radius = 42 + round(18 * (1 - math.cos(i / 23 * math.pi)) / 2)
        for r in (radius, radius + 15):
            d.ellipse((280 - r, 112 - r, 280 + r, 112 + r), outline=theme.color, width=2)
        glyph(d, (280, 112), 30, theme.motif, theme.color, 3)
        for j in range(8):
            angle = j * math.pi / 4 + i / 23 * 0.65
            x, y = 280 + math.cos(angle) * 86, 112 + math.sin(angle) * 86
            d.ellipse((x - 2, y - 2, x + 2, y + 2), fill="#f7eefb")
        d.text(
            (280, 223), "A DORMANT SIGNATURE ANSWERS", font=font(16), fill="#f7eefb", anchor="mm"
        )
        frames.append(image.quantize(palette=palette, dither=Image.Dither.NONE))
    output = BytesIO()
    durations = [70] * 24
    durations[-1] = 400
    frames[0].save(
        output,
        "GIF",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        disposal=1,
        optimize=False,
    )
    return output.getvalue()
