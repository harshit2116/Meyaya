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


def masked_bar(draw, x, y, current, maximum, width=360, label="HP", color=None):
    color = color or (PINK if label == "HP" else LILAC)
    draw.text((x, y - 25), f"{label} // UNKNOWN", font=font(17), fill=color)
    draw.rounded_rectangle((x, y, x + width, y + 18), radius=6, fill="#261f36")
    extent = width * max(0, min(1, current / max(1, maximum)))
    if extent > 0:
        draw.rounded_rectangle((x, y, x + max(2, extent), y + 18), radius=2, fill=color)
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
    if not intro:
        from bot.services.boss_battle_cards import render_boss_arena, render_boss_defeat

        renderer = render_boss_defeat if state.finished else render_boss_arena
        return renderer(state, portraits, palettes)
    try:
        if state.left.is_boss:
            return render_patron_clash(state, intro=intro)
        return render_boss_encounter(state, portraits, palettes, intro=intro)
    except OSError:
        if state.right.boss_key == "veyra" or state.left.is_boss:
            raise
        pass
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


def render_boss_encounter(state, portraits, palettes, *, intro=False):
    player, boss = state.left, state.right
    erasure = boss.boss_key == "veyra"
    PINK, LILAC, CYAN = (
        ("#ff617e", "#b69ad9", "#f5b4c4") if erasure else ("#f3b2dc", "#c4a7ee", "#a8ecec")
    )
    name = "VEYRA" if erasure else "MEYAYA"
    recorded = "VOID REVENANT" if erasure else "SOULWEAVER"
    threat = "ANNIHILATION CLASS" if erasure else "BEYOND MEASUREMENT"
    accent = palettes[0][0] if palettes and palettes[0] else "#e9b38d"
    image = Image.new("RGB", DUEL_SIZE, "#090911")
    source = template("veyra-profile.png" if erasure else "meyaya-profile.png")
    artwork = source.crop((0, 0, round(source.width * 0.63), source.height))
    artwork = ImageOps.fit(artwork, (635, 565), Image.Resampling.LANCZOS, centering=(0.5, 0.16))
    image.paste(artwork, (465, 0))
    veil = Image.new("RGBA", DUEL_SIZE)
    shade = ImageDraw.Draw(veil)
    for horizontal in range(465, 650):
        shade.line(
            (horizontal, 0, horizontal, 565), fill=(9, 9, 17, round(245 * (650 - horizontal) / 185))
        )
    for vertical in range(565):
        alpha = max(35, min(245, round((vertical - 230) * 0.85)))
        shade.line((465, vertical, 1100, vertical), fill=(13, 8, 23, alpha))
    shade.rectangle((0, 0, 1100, 56), fill=(9, 9, 17, 225))
    image = Image.alpha_composite(image.convert("RGBA"), veil).convert("RGB")
    draw = ImageDraw.Draw(image)
    draw.line((30, 56, 1070, 56), fill=PINK, width=1)
    fit(draw, (265, 29), "SOUL INTERFACE  /  AUTHORITY OVERRIDE", 16, width=475, color=LILAC)
    fit(
        draw,
        (868, 29),
        "FINAL BOSS  //  ERASURE ACTIVE" if erasure else "FINAL BOSS  //  ORIGIN PROTOCOL",
        15,
        width=420,
        color=PINK,
    )
    draw.polygon(((445, 78), (478, 78), (515, 530), (482, 530)), fill="#211326")
    draw.line((461, 78, 499, 530), fill=PINK, width=2)
    fit(draw, (228, 87), "CHALLENGER", 14, width=370, color=accent)
    art = portrait(portraits[0], player.name, 170)
    mask = Image.new("L", (170, 170))
    ImageDraw.Draw(mask).ellipse((0, 0, 169, 169), fill=255)
    image.paste(art, (143, 115), mask)
    draw.ellipse((137, 109, 319, 291), outline=accent, width=2)
    draw.arc((126, 98, 330, 302), 35, 155, fill=PINK, width=3)
    draw.arc((126, 98, 330, 302), 215, 335, fill=CYAN, width=3)
    fit(draw, (228, 324), player.name, 32, width=390)
    fit(draw, (228, 359), player.title, 17, width=390, color=accent)
    fit(
        draw,
        (228, 390),
        f"{player.class_name} · Lv {player.level} · {player.affinity_name}",
        16,
        width=395,
        color=LILAC,
    )
    if intro:
        draw.polygon(
            ((490, 212), (571, 292), (490, 372), (409, 292)), fill="#130d20", outline=PINK, width=3
        )
        fit(draw, (490, 292), "VS", 64, width=135, color="#fff1fa")
        fit(draw, (816, 310), name, 65, width=455, color="#fff1fa")
        fit(
            draw,
            (816, 362),
            "ENEMY OF ALL" if erasure else "THE UNFAIR FINAL BOSS",
            20,
            width=455,
            color=PINK,
        )
        fit(draw, (816, 402), state.boss_form.upper(), 25, width=455, color="#fff1fa")
        fit(draw, (228, 465), "ONE SOUL.", 26, width=375, color=accent)
        fit(draw, (228, 502), "ONE IMPOSSIBLE OPPONENT.", 17, width=375, color=LILAC)
        fit(draw, (816, 470), f"RECORDED: {recorded}", 16, width=455, color=CYAN)
        fit(draw, (816, 502), f"THREAT: {threat}", 16, width=455, color=PINK)
        draw.rectangle((0, 558, 1100, 640), fill="#0c0b15")
        draw.line((30, 558, 1070, 558), fill="#684059", width=1)
        fit(
            draw,
            (550, 583),
            "THE SOUL INTERFACE HAS ACCEPTED YOUR CHALLENGE",
            18,
            width=1010,
            color=PINK,
        )
        fit(draw, (550, 616), state.counter_pattern, 15, width=1010, color=LILAC)
        return encode(image)
    for vertical, label, value, maximum, color in (
        (438, "HP", player.hp, player.max_hp, accent),
        (498, "MP", player.mp, player.max_mp, CYAN),
    ):
        draw.text((42, vertical - 24), label, font=font(15), fill=color)
        draw.text(
            (412, vertical - 24), f"{value} / {maximum}", font=font(15), fill="#fff0fa", anchor="ra"
        )
        draw.rounded_rectangle((42, vertical, 412, vertical + 10), radius=3, fill="#252032")
        extent = round(370 * max(0, min(1, value / max(1, maximum))))
        if extent:
            draw.rectangle((42, vertical, 42 + extent, vertical + 10), fill=color)
    fit(draw, (801, 310), name, 68, width=510, color="#fff1fa")
    fit(
        draw,
        (801, 361),
        "ENEMY OF ALL" if erasure else "THE GIRL AT THE END OF EVERY STORY",
        15,
        width=510,
        color=PINK,
    )
    fit(draw, (801, 395), state.boss_form.upper(), 25, width=510, color="#fff1fa")
    fit(draw, (801, 422), f"{recorded}  /  ANALYSIS DENIED", 13, width=510, color=CYAN)
    masked_bar(draw, 556, 464, boss.hp, boss.max_hp, width=490, color=PINK)
    masked_bar(draw, 556, 519, boss.mp, boss.max_mp, width=490, label="MP", color=LILAC)
    draw.rectangle((0, 558, 1100, 640), fill="#0c0b15")
    draw.line((30, 558, 1070, 558), fill="#684059", width=1)
    status = (
        f"MOVE {state.moves:02}  /  {'ABYSS' if erasure else 'SPELL'} MEMORY {state.memory_count}"
    )
    fit(draw, (228, 586), status, 15, width=400, color=PINK)
    fit(draw, (228, 616), f"THREAT: {threat}", 13, width=400, color=LILAC)
    events = state.history[-2:] if not intro else [state.counter_pattern, state.dialogue]
    for index, event in enumerate(events):
        fit(draw, (795, 584 + index * 28), event, 14, width=535, color="#f4e6f0")
    return encode(image)


def render_patron_clash(state, *, intro=False):
    image = Image.new("RGB", DUEL_SIZE, "#0b0813")
    for index, fighter in enumerate((state.left, state.right)):
        source = template(f"{fighter.boss_key}-profile.png")
        artwork = source.crop((0, 0, round(source.width * 0.63), source.height))
        artwork = ImageOps.fit(artwork, (550, 560), Image.Resampling.LANCZOS, centering=(0.5, 0.15))
        image.paste(artwork, (index * 550, 0))
    veil = Image.new("RGBA", DUEL_SIZE)
    shade = ImageDraw.Draw(veil)
    for vertical in range(560):
        shade.line(
            (0, vertical, 1100, vertical),
            fill=(10, 5, 18, max(15, min(240, round((vertical - 170) * 0.75)))),
        )
    shade.rectangle((0, 0, 1100, 64), fill=(10, 5, 18, 220))
    image = Image.alpha_composite(image.convert("RGBA"), veil).convert("RGB")
    draw = ImageDraw.Draw(image)
    fit(
        draw,
        (550, 31),
        "ORIGIN  /  ERASURE     —     WORLD COLLISION",
        21,
        width=1030,
        color="#fff0f7",
    )
    for offset in (-8, 0, 8):
        draw.line(
            (
                548 + offset,
                70,
                523 + offset,
                185,
                578 + offset,
                275,
                532 + offset,
                390,
                553 + offset,
                545,
            ),
            fill=PINK if offset else "#fff4fc",
            width=2 if offset else 4,
        )
    if not intro:
        phase = min(2, state.moves // 4)
        for shard in range(8 + phase * 6):
            horizontal = 420 + (shard * 83 + state.moves * 13) % 260
            vertical = 80 + (shard * 71 + state.moves * 9) % 430
            radius = 8 + (shard % 3) * 5
            draw.polygon(
                (
                    (horizontal, vertical - radius),
                    (horizontal + radius, vertical + 4),
                    (horizontal - 4, vertical + radius),
                ),
                outline=PINK if shard % 2 else "#ff617e",
            )
    for index, fighter in enumerate((state.left, state.right)):
        center = 265 if index == 0 else 835
        color = PINK if index == 0 else "#ff617e"
        fit(draw, (center, 310), fighter.name.upper(), 52, width=455, color="#fff4fc")
        fit(
            draw,
            (center, 355),
            "BLOOM OF ORIGIN" if index == 0 else "ENEMY OF ALL",
            20,
            width=455,
            color=color,
        )
        if intro:
            fit(
                draw,
                (center, 445),
                "EVERBLOOM" if index == 0 else "MOURNFANG",
                23,
                width=440,
                color=color,
            )
            fit(
                draw,
                (center, 488),
                "THE FIRST DAWN" if index == 0 else "THE LAST SILENCE",
                16,
                width=440,
                color=LILAC,
            )
        else:
            masked_bar(draw, center - 210, 439, fighter.hp, fighter.max_hp, width=420, color=color)
            masked_bar(draw, center - 210, 500, fighter.mp, fighter.max_mp, width=420, label="MP")
    if intro:
        draw.polygon(
            ((550, 220), (615, 285), (550, 350), (485, 285)), fill="#160c20", outline=PINK, width=2
        )
        fit(draw, (550, 284), "VS", 49, width=115)
    draw.rectangle((0, 553, 1100, 640), fill="#0c0813")
    fit(
        draw,
        (550, 576),
        "TWO AUTHORITIES. ONE SURVIVING REALITY." if intro else state.boss_form,
        21,
        width=1040,
        color=PINK,
    )
    event = (
        state.history[-1]
        if state.history and not intro
        else "THE SOUL INTERFACE CAN NO LONGER GUARANTEE REALITY."
    )
    fit(draw, (550, 614), event, 15, width=1040, color="#f6e3ef")
    return encode(image)


def render_boss_profile(profile, avatar=b""):
    # The new full illustration is authoritative, with no avatar overlay.
    return render_patron_profile("meyaya")


@lru_cache(maxsize=2)
def render_patron_profile(patron):
    if patron not in {"meyaya", "veyra"}:
        raise ValueError("Unknown patron profile")
    return encode(template(f"{patron}-profile.png"))
