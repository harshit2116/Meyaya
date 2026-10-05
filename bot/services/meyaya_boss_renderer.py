"""Local floral/prismatic boss UI; only bars can reveal resource progress."""

from io import BytesIO
from functools import lru_cache
from pathlib import Path
import math
from PIL import Image, ImageDraw, ImageOps
from bot.services.card_renderer import font
from bot.services.fantasy_render import portrait, flower, blend
from bot.services.fantasy_duel_renderer import fit, DUEL_SIZE

PINK = "#f3b2dc"
LILAC = "#c4a7ee"
CYAN = "#a8ecec"
ASSETS = Path(__file__).resolve().parents[1] / "assets" / "duels"


@lru_cache(maxsize=3)
def template(name):
    with Image.open(ASSETS / name) as source:
        return source.convert("RGB")


def render_boss_opening(state, portraits, palettes):
    """Supplied illustrated backdrop; all challenger identity is rendered live."""
    image = ImageOps.fit(template("meyaya-challenge.png"), DUEL_SIZE, Image.Resampling.LANCZOS)
    accent = palettes[0][0] if palettes and palettes[0] else "#e9b38d"
    # Recolour the challenger's energy, preserving fine texture and boss colours.
    left = image.crop((0, 0, 550, 640))
    coloured = ImageOps.colorize(ImageOps.grayscale(left), "#100c18", accent)
    image.paste(Image.blend(left, coloured, 0.60), (0, 0))
    overlay = Image.new("RGBA", DUEL_SIZE)
    d = ImageDraw.Draw(overlay)
    # Hide the sample's baked-in names/stats; never present Ayaya for another user.
    d.rectangle((0, 300, 1100, 640), fill=(15, 10, 25, 255))
    d.rectangle((405, 245, 695, 382), fill=(15, 10, 25, 255))
    image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    d = ImageDraw.Draw(image)
    for i, fighter in enumerate((state.left, state.right)):
        x = 265 if i == 0 else 835
        art = portrait(portraits[i], fighter.name, 210)
        mask = Image.new("L", (210, 210))
        ImageDraw.Draw(mask).ellipse((0, 0, 209, 209), fill=255)
        image.paste(art, (x - 105, 74), mask)
        d.ellipse((x - 110, 69, x + 110, 289), outline=accent if i == 0 else PINK, width=3)
        fit(d, (x, 329), fighter.name, 42, width=470, color=accent if i == 0 else PINK)
        fit(d, (x, 373), fighter.title, 21, width=470, color="#fff0fa")
        fit(
            d,
            (x, 414),
            state.boss_form if i else f"{fighter.class_name} · Lv {fighter.level}",
            23,
            width=470,
        )
        fit(
            d,
            (x, 450),
            "RECORDED: SOULWEAVER / ANALYSIS FAILED" if i else fighter.affinity_name,
            15,
            width=470,
            color=CYAN if i else accent,
        )
        if i:
            masked_bar(d, 655, 500, fighter.hp, fighter.max_hp)
            masked_bar(d, 655, 558, fighter.mp, fighter.max_mp, label="MP")
            fit(d, (x, 605), "BEYOND MEASUREMENT", 16, width=470, color=PINK)
        else:
            for y, label, current, maximum in (
                (500, "HP", fighter.hp, fighter.max_hp),
                (558, "MP", fighter.mp, fighter.max_mp),
            ):
                d.text(
                    (85, y - 25), f"{label} {current} / {maximum}", font=font(17), fill="#fff0fa"
                )
                d.rounded_rectangle((85, y, 445, y + 18), radius=6, fill=accent)
    fit(d, (550, 276), "VS", 89, width=185, color="#fff0fa")
    fit(d, (550, 590), "AUTHORITY OVERRIDE", 12, width=175, color=LILAC)
    return encode(image)


def prism_canvas(size):
    image = Image.new("RGB", size, "#151223")
    d = ImageDraw.Draw(image)
    w, h = size
    for y in range(h):
        d.line(
            (w // 2, y, w, y),
            fill=blend((26, 20, 39), (102, 62, 106), 0.25 + 0.25 * math.sin(y / h * math.pi)),
        )
    for n in range(22):
        x = w // 2 + (n * 79) % (w // 2 - 30)
        y = 40 + (n * 97) % (h - 80)
        d.polygon(((x, y - 23), (x + 15, y), (x, y + 25), (x - 10, y)), outline="#65516f")
        d.line((x, y - 23, x, y + 25), fill="#436166")
        if n % 4 == 0:
            flower(d, x, y, 10, "#73546d")
    for y in range(185, h - 30, 31):
        d.line((w // 2 + 25, y, w - 20, y), fill="#463047")
    return image


def masked_bar(draw, x, y, current, maximum, width=360, label="HP"):
    draw.text((x, y - 25), f"{label} // UNKNOWN", font=font(17), fill=PINK)
    draw.rounded_rectangle((x, y, x + width, y + 18), radius=6, fill="#261f36")
    extent = width * max(0, min(1, current / max(1, maximum)))
    if extent > 0:
        draw.rounded_rectangle(
            (x, y, x + max(2, extent), y + 18), radius=2, fill=PINK if label == "HP" else LILAC
        )
        for offset in range(10, int(extent), 24):
            draw.line((x + offset, y, x + offset + 4, y + 18), fill="#fff0f7", width=2)
    draw.text((x + width, y - 25), "??? / ???", font=font(17), fill="#fff4fc", anchor="ra")


def encode(image):
    output = BytesIO()
    image.save(output, "PNG")
    if output.tell() > 4 * 1024 * 1024:
        raise ValueError("Boss card exceeds upload budget")
    return output.getvalue()


def render_boss_duel(state, portraits, palettes, *, intro=False):
    if intro:
        return render_boss_opening(state, portraits, palettes)
    image = prism_canvas(DUEL_SIZE)
    d = ImageDraw.Draw(image)
    player, boss = state.left, state.right
    accent = palettes[0][0] if palettes and palettes[0] else "#e9b38d"
    d.rounded_rectangle((18, 18, 1082, 622), radius=20, outline=LILAC)
    fit(d, (550, 40), "SOUL INTERFACE / AUTHORITY OVERRIDE", 17, width=800, color=PINK)
    for index, fighter in enumerate((player, boss)):
        x = 250 if index == 0 else 850
        fit(d, (x, 79), fighter.name, 30, width=420)
        fit(d, (x, 114), fighter.title, 18, width=435, color=accent if index == 0 else PINK)
        art = portrait(portraits[index], fighter.name, 210)
        mask = Image.new("L", (210, 210))
        ImageDraw.Draw(mask).ellipse((0, 0, 209, 209), fill=255)
        image.paste(art, (x - 105, 151), mask)
        d.ellipse((x - 112, 144, x + 112, 368), outline=accent if index == 0 else PINK, width=3)
        if index == 1:
            # Everbloom spellcrown: orbiting petals and displaced glass border.
            d.arc((x - 137, 127, x + 137, 385), 190, 350, fill=CYAN, width=2)
            for n in range(7):
                theta = n / 7 * math.pi * 2
                px, py = x + math.cos(theta) * 132, 255 + math.sin(theta) * 132
                flower(d, px, py, 10, PINK)
            fit(d, (x, 397), state.boss_form, 24, width=430, color=PINK)
            fit(d, (x, 426), "RECORDED: SOULWEAVER / ANALYSIS FAILED", 14, width=435, color=CYAN)
            masked_bar(d, 670, 477, boss.hp, boss.max_hp)
            masked_bar(d, 670, 535, boss.mp, boss.max_mp, label="MP")
            fit(d, (x, 594), "BEYOND MEASUREMENT", 18, width=420, color=PINK)
        else:
            fit(d, (x, 397), player.class_name + f" · Lv {player.level}", 24, width=420)
            fit(d, (x, 426), player.affinity_name, 18, width=420, color=accent)
            for y, label, value, total in (
                (477, "HP", player.hp, player.max_hp),
                (535, "MP", player.mp, player.max_mp),
            ):
                d.text((70, y - 25), f"{label} {value} / {total}", font=font(17), fill="#fff0f7")
                d.rounded_rectangle((70, y, 430, y + 18), radius=7, fill="#242135")
                extent = 360 * max(0, min(1, value / max(1, total)))
                if extent:
                    d.rounded_rectangle((70, y, 70 + max(2, extent), y + 18), radius=2, fill=accent)
    if state.finished:
        label = (
            "MEYAYA DEFEATED"
            if state.winner_id == player.user_id
            else "DRAW" if state.winner_id is None else "MEYAYA WINS"
        )
        fit(d, (550, 180), label, 26, width=240, color=PINK)
        fit(
            d,
            (250, 594),
            (
                "WON"
                if state.winner_id == player.user_id
                else "DRAW" if state.winner_id is None else "DEFEATED"
            ),
            28,
            width=420,
        )
        fit(d, (550, 265), "✦", 70, width=150, color=CYAN)
        fit(d, (550, 383), f"MEMORY · {state.memory_count}", 16, width=190, color=PINK)
        fit(d, (550, 570), state.finisher or state.verdict, 13, width=240, color=LILAC)
    else:
        fit(
            d,
            (550, 252),
            "VS" if intro else f"{state.moves}",
            100 if intro else 55,
            width=190,
            color=PINK,
        )
        fit(
            d,
            (550, 356),
            "THE UNFAIR FINAL BOSS" if intro else "SOUL PRESSURE",
            13,
            width=190,
            color=CYAN,
        )
        if not intro:
            fit(d, (550, 395), "UNREADABLE", 15, width=190, color=PINK)
    return encode(image)


def render_boss_profile(profile, avatar=b""):
    # The new full illustration is authoritative, with no avatar overlay.
    return render_patron_profile("meyaya")


def render_patron_profile(patron):
    if patron not in {"meyaya", "veyra"}:
        raise ValueError("Unknown patron profile")
    return encode(template(f"{patron}-profile.png"))
