"""Five compact, distinct local layouts; no model or network dependencies."""

from functools import lru_cache
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from random import Random
import math
from PIL import Image, ImageDraw, ImageFont, ImageOps
from bot.services.celestial import definitions

ASSETS = Path(__file__).resolve().parents[1] / "assets" / "celestial"
SIZES = {
    "tarot": (1080, 900),
    "fortune": (1000, 900),
    "fate": (1000, 780),
    "summon": (1000, 740),
    "guardian": (1000, 620),
}
GUARDIANS = {
    "Velvet Owl": "owl",
    "Comet Fox": "fox-head",
    "Moss Dragon": "dragon-head",
    "Pearl Moth": "star-swirl",
}


@lru_cache(maxsize=24)
def font(size):
    for path in ("C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def lines(draw, value, size, width):
    result, line = [], ""
    for char in str(value):
        if char == "\n" or draw.textlength(line + char, font=font(size)) > width:
            # Prefer a word boundary.
            if char != "\n" and " " in line:
                head, tail = line.rsplit(" ", 1)
                result.append(head)
                line = tail + char
            else:
                result.append(line)
                line = "" if char == "\n" else char
        else:
            line += char
    if line:
        result.append(line)
    return result


def label(draw, box, value, size=26, color="#eee8dc", minimum=16):
    x, y, w, h = box
    while size > minimum and len(lines(draw, value, size, w)) * (size + 6) > h:
        size -= 1
    wrapped = lines(draw, value, size, w)
    count = max(1, h // (size + 6))
    if len(wrapped) > count:
        wrapped = wrapped[:count]
        wrapped[-1] = wrapped[-1][:-3] + "..."
    for line in wrapped:
        draw.text((x, y), line, font=font(size), fill=color)
        y += size + 6


def load_art(path):
    try:
        with Image.open(path) as art:
            return art.convert("RGBA")
    except (OSError, ValueError):
        return None


def paste(image, art, box, cover=False):
    x, y, w, h = box
    art = ImageOps.fit(art, (w, h)) if cover else ImageOps.contain(art, (w, h))
    image.paste(
        art,
        (x + (w - art.width) // 2, y + (h - art.height) // 2),
        art if art.mode == "RGBA" else None,
    )


def base(kind, color, accent):
    image = Image.new("RGB", SIZES[kind], color)
    background = load_art(ASSETS / "backgrounds/violet.png")
    if background is not None and kind != "fortune":
        background = ImageOps.fit(background.convert("RGB"), image.size)
        image = Image.blend(image, background, 0.16 if kind != "guardian" else 0.10)
    d = ImageDraw.Draw(image)
    w, h = image.size
    d.rounded_rectangle((14, 14, w - 15, h - 15), radius=22, outline=accent, width=2)
    return image, d


def header(image, draw, result, name, accent, avatar):
    label(draw, (36, 30, 800, 30), result.kind.upper() + "  /  " + result.day, 19, accent)
    label(draw, (36, 68, 800, 42), name, 30)
    if avatar:
        try:
            if len(avatar) > 6 * 1024 * 1024:
                raise ValueError("Avatar is too large")
            with Image.open(BytesIO(avatar)) as source:
                if source.width * source.height > 4_000_000:
                    raise ValueError("Avatar dimensions are too large")
                source.thumbnail((1024, 1024))
                art = source.convert("RGBA")
            mask = Image.new("L", (58, 58))
            ImageDraw.Draw(mask).ellipse((0, 0, 57, 57), fill=255)
            art = ImageOps.fit(art, (58, 58))
            image.paste(art, (image.width - 100, 36), mask)
        except (OSError, ValueError):
            pass


def tile(draw, box, title, value, accent, fill="#222339", size=26, text_color="#eee8dc"):
    x, y, w, h = box
    draw.rounded_rectangle((x, y, x + w, y + h), radius=12, fill=fill)
    label(draw, (x + 16, y + 12, w - 32, 25), title.upper(), 16, accent)
    label(draw, (x + 16, y + 43, w - 32, h - 51), value, size, text_color)


def tarot(image, d, r):
    accent = "#dbbd7a"
    label(d, (36, 123, 990, 45), "THREE THREADS OF YOUR STORY", 32, accent)
    names = [c[0] for c in definitions()["tarot"]]
    for i, (position, title, meaning) in enumerate(r.panels):
        x = 36 + i * 338
        d.rounded_rectangle((x, 188, x + 320, 864), radius=16, fill="#e8dbc0")
        label(d, (x + 16, 201, 288, 32), position.upper(), 21, "#59442e")
        number = names.index(title.removesuffix(" (R)"))
        art = load_art(ASSETS / "tarot" / f"{number:02d}.jpg")
        if art is not None:
            if title.endswith(" (R)"):
                art = art.transpose(Image.Transpose.ROTATE_180)
            paste(image, art, (x + 18, 244, 284, 425))
        else:
            label(d, (x + 30, 385, 260, 100), "Artwork unavailable", 26, "#59442e")
        label(d, (x + 18, 687, 284, 65), title, 26, "#30273b")
        label(d, (x + 18, 765, 284, 83), meaning, 22, "#59442e")


def fortune(image, d, r):
    f = dict(r.fields)
    ink, muted, gold = "#f6eee6", "#bdb0ce", "#e8c893"
    # A dark editorial reading: one hero, three compact tokens, two clear takeaways.
    d.rounded_rectangle((32, 124, 968, 444), radius=26, fill="#262039", outline="#51435e", width=2)
    label(d, (60, 151, 590, 24), "YOUR DAILY CHAPTER", 15, gold)
    label(d, (60, 196, 575, 106), r.title, 40, ink)
    label(d, (60, 324, 575, 92), f["Outlook"], 22, muted)
    luck = max(0, min(100, int(f["Luck"].split("/")[0])))
    d.ellipse((706, 173, 918, 385), fill="#191626", outline="#51435e", width=2)
    d.arc((715, 182, 909, 376), start=-90, end=-90 + max(1, luck * 3.6), fill=gold, width=7)
    d.text((812, 231), "TODAY'S LUCK", font=font(14), fill=muted, anchor="mm")
    d.text((812, 285), str(luck), font=font(64), fill=ink, anchor="mm")
    d.text((812, 338), "OUT OF 100", font=font(13), fill=gold, anchor="mm")
    for i, key in enumerate(("Lucky number", "Color", "Lucky theme")):
        x = 32 + i * 318
        tile(d, (x, 463, 300, 99), key, f[key], gold, fill="#292239", size=23, text_color=ink)
    for x, key in ((32, "Omen"), (510, "Advice")):
        tile(d, (x, 581, 458, 134), key, f[key], gold, fill="#211d30", size=23, text_color=ink)
    oracle = f.get("Question oracle")
    if oracle:
        tile(d, (32, 734, 936, 96), "Your question / the oracle answers", oracle, gold,
             fill="#30263c", size=23, text_color=ink)
    else:
        d.line((60, 756, 940, 756), fill="#51435e", width=1)
        label(d, (60, 777, 880, 28), "A little perspective for today. Your choices still write the story.", 20, muted)
    label(d, (60, 851, 880, 23), "MEYAYA  /  FOR FUN, NOT A PREDICTION  /  RETURNS DAILY", 13, gold, minimum=13)


def fate(image, d, r):
    f = dict(r.fields)
    accent = "#c5b1ff"
    gold = "#e3c77d"
    panel = "#292442"
    d.rounded_rectangle((28, 120, 972, 750), radius=24, fill="#18162f", outline=accent, width=2)
    d.ellipse((55, 151, 173, 269), outline=gold, width=2)
    d.ellipse((73, 169, 155, 251), outline="#76669c", width=2)
    d.polygon(((114, 181), (132, 210), (114, 239), (96, 210)), fill=gold)
    d.polygon(((114, 194), (123, 210), (114, 226), (105, 210)), fill="#18162f")
    label(d, (204, 145, 720, 55), r.title, 42, accent)
    label(d, (207, 205, 680, 28), "THE ARCHETYPE WALKING BESIDE YOU", 16, gold)
    tile(d, (54, 286, 892, 112), "What this fate means", f["Meaning"], gold, fill=panel, size=23)
    for i, (k, v) in enumerate((("Path", f["Path"]), ("Core strength", f["Strength"]))):
        x = 54 + i * 454
        tile(d, (x, 418, 438, 94), k, v, accent, fill="#30294c", size=26)
    tile(
        d,
        (54, 532, 892, 92),
        "The chapter ahead",
        f["Possible chapter"],
        accent,
        fill=panel,
        size=23,
    )
    tile(d, (54, 644, 550, 82), "Guidance", f["Guidance"], gold, fill="#30294c", size=19)
    tile(d, (620, 644, 326, 82), "Omen", f["Omen"], gold, fill="#30294c", size=18)


def summon(image, d, r):
    f = dict(r.fields)
    accent = {"3 stars": "#98d7c5", "4 stars": "#c5a8fc", "5 stars": "#f0cc75"}[f["Rarity"]]
    character = definitions()["characters"][r.title]
    label(d, (36, 119, 930, 58), r.title, 40, accent)
    # A hero plate on the left, combat kit on the right.
    d.rounded_rectangle((30, 190, 410, 704), radius=18, fill="#101725", outline=accent, width=2)
    sheet = load_art(ASSETS / "portraits/lorestrome.jpg")
    if sheet:
        index = character["portrait_index"]
        col, row = index % 6, index // 6
        art = sheet.crop((col * 300, row * 300, (col + 1) * 300, (row + 1) * 300))
        paste(image, art, (42, 202, 356, 356), True)
    label(d, (50, 570, 340, 48), f["Hero"], 36, accent)
    stars = int(f["Rarity"][0])
    for i in range(stars):
        cx, cy = 63 + i * 32, 641
        points = [
            (
                cx + (12 if j % 2 == 0 else 5) * math.cos(-math.pi / 2 + j * math.pi / 5),
                cy + (12 if j % 2 == 0 else 5) * math.sin(-math.pi / 2 + j * math.pi / 5),
            )
            for j in range(10)
        ]
        d.polygon(points, fill=accent)
    label(d, (50, 665, 340, 27), f["Affinity"].upper() + " / ORIGINAL HERO", 17, accent)
    tile(d, (430, 190, 532, 80), "Class", f["Role"], accent)
    stats = f["Power / Guard / Spirit"].split(" / ")
    for i, (key, value) in enumerate(zip(("Power", "Guard", "Spirit"), stats)):
        x = 430 + i * 181
        tile(d, (x, 284, 170, 97), key, value, accent, size=29)
        d.rounded_rectangle((x + 16, 366, x + 154, 370), radius=2, fill="#42465b")
        d.rounded_rectangle(
            (x + 16, 366, x + 16 + int(138 * int(value) / 100), 370), radius=2, fill=accent
        )
    tile(
        d, (430, 396, 532, 95), "Signature release", f["Signature"], accent, fill="#343047", size=25
    )
    tile(d, (430, 505, 532, 93), "Passive", f["Passive"], accent, size=23)
    tile(d, (430, 612, 532, 92), "Drawback", f["Shadow"], accent, size=23)


def guardian(image, d, r):
    f = dict(r.fields)
    accent = "#94e1cd"
    label(d, (36, 124, 925, 58), r.title, 40, accent)
    icon = load_art(ASSETS / "icons" / (GUARDIANS.get(r.title, "owl") + ".png"))
    d.ellipse((55, 198, 365, 508), outline=accent, width=2)
    d.ellipse((75, 218, 345, 488), outline="#37655f", width=1)
    if icon:
        paste(image, icon, (102, 245, 216, 216))
    label(d, (48, 526, 335, 58), f["Type"], 24, accent)
    tile(d, (400, 199, 272, 90), "Affinity", f["Affinity"], accent, fill="#173c39")
    tile(d, (688, 199, 272, 90), "Bond", f["Bond"], accent, fill="#173c39")
    tile(d, (400, 305, 560, 120), "Blessing", f["Blessing"], accent, fill="#173c39")
    tile(d, (400, 441, 560, 120), "Weakness", f["Weakness"], accent, fill="#173c39")
    label(
        d,
        (400, 577, 550, 22),
        "Icon: Lorc / game-icons.net / CC BY 3.0 (resized)",
        14,
        "#8cb7ae",
        minimum=14,
    )


def render_card(result, name, avatar=b""):
    colors = {
        "tarot": ("#221a30", "#dbbd7a"),
        "fortune": ("#14121f", "#e8c893"),
        "fate": ("#1c1835", "#bdacfa"),
        "summon": ("#171f2c", "#d6b784"),
        "guardian": ("#102c2c", "#94e1cd"),
    }
    image, d = base(result.kind, *colors[result.kind])
    header(image, d, result, name, colors[result.kind][1], avatar)
    {"tarot": tarot, "fortune": fortune, "fate": fate, "summon": summon, "guardian": guardian}[
        result.kind
    ](image, d, result)
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
