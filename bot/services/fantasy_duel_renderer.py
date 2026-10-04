"""Bounded per-move still cards: profile-palette split screen and clash art."""

from io import BytesIO
import math
from PIL import Image, ImageDraw, ImageEnhance, ImageOps
from bot.services.card_renderer import font
from bot.services.fantasy_render import portrait, rgb, blend
from bot.data.fantasy import RARITIES

DUEL_SIZE = (1100, 640)


def fit(draw, pos, text, size=23, color="#f5f0fa", width=370, anchor="mm"):
    text = " ".join(str(text).split())[:150]
    while size > 12 and draw.textlength(text, font=font(size)) > width:
        size -= 1
    while text and draw.textlength(text, font=font(size)) > width:
        text = text[:-2] + "…"
    draw.text(pos, text, font=font(size), fill=color, anchor=anchor)


def render_duel(state, portraits=(b"", b""), palettes=((), ()), *, intro=False):
    image = Image.new("RGB", DUEL_SIZE)
    d = ImageDraw.Draw(image)
    arena, dark, arena_accent, motif = state.arena
    colors = [rgb(palette[0]) if palette else rgb(arena_accent) for palette in palettes]
    secondary = [
        rgb(palette[1]) if len(palette) > 1 else color for palette, color in zip(palettes, colors)
    ]
    for y in range(640):
        intensity = 0.16 + 0.24 * max(0, 1 - abs(y - 250) / 390)
        for index, (start, end) in enumerate(((0, 550), (550, 1100))):
            tint = blend(colors[index], secondary[index], y / 640)
            d.line((start, y, end, y), fill=blend(rgb(dark), tint, intensity))
    # Soft palette-coloured halos behind the portraits, not a new bitmap asset.
    from PIL import ImageFilter

    glow = Image.new("RGB", DUEL_SIZE)
    gd = ImageDraw.Draw(glow)
    for x, color in zip((250, 850), colors):
        gd.ellipse((x - 150, 88, x + 150, 388), fill=blend((0, 0, 0), color, 0.36))
    # ImageChops.screen is additive while preserving the dark arena background.
    from PIL import ImageChops

    image = ImageChops.screen(image, glow.filter(ImageFilter.GaussianBlur(45)))
    d = ImageDraw.Draw(image)
    # Original geometric energy shards, tinted from each member's profile.
    for side in (0, 1):
        accent = blend(colors[side], (240, 235, 255), 0.5)
        direction = 1 if side == 0 else -1
        for n in range(12):
            x = 550 + direction * (-70 - n * 22)
            y = 90 + (n * 47) % 350
            d.polygon(
                ((x, y), (x + direction * 90, y + 40), (x + direction * 30, y + 52)),
                fill=blend((10, 12, 24), colors[side], 0.4),
            )
            d.line((x, y, x + direction * 70, y + 32), fill=accent, width=1)
        for n in range(24):
            x = (n * 173 + side * 89) % 480 + side * 620
            y = (n * 67) % 500 + 40
            d.ellipse((x, y, x + 2, y + 2), fill=accent)
    seam = [(550 + math.sin(y / 26) * 8, y) for y in range(50, 615, 8)]
    d.line(seam, fill="#ded9f1", width=2)
    if motif == "moon":
        d.arc((470, 80, 630, 240), 30, 325, fill=arena_accent, width=2)
    elif motif == "petals":
        for n in range(7):
            x, y = 508 + (n * 31) % 90, 100 + n * 23
            d.ellipse((x, y, x + 12, y + 5), fill=arena_accent)
    else:
        d.polygon(((550, 105), (623, 188), (550, 324), (477, 188)), outline=arena_accent, width=2)
    d.rounded_rectangle((15, 15, 1084, 624), radius=22, outline="#625b76", width=1)
    fit(d, (550, 39), "M E Y A Y A  /  F A N T A S Y  D U E L", 16, width=700)

    for index, (fighter, x) in enumerate(((state.left, 250), (state.right, 850))):
        accent = blend(colors[index], (245, 230, 250), 0.45)
        art = portrait(portraits[index], fighter.name, 236)
        defeated = (
            state.finished and state.winner_id is not None and fighter.user_id != state.winner_id
        )
        winner = state.finished and fighter.user_id == state.winner_id
        acting = not intro and not state.finished and state.last_actor == fighter.user_id
        if defeated:
            art = ImageEnhance.Brightness(ImageOps.grayscale(art).convert("RGB")).enhance(0.45)
        mask = Image.new("L", (236, 236))
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, 235, 235), radius=38, fill=255)
        image.paste(art, (x - 118, 113), mask)
        d.rounded_rectangle(
            (x - 123, 108, x + 123, 354),
            radius=40,
            outline="#efd493" if winner else "#fff0fb" if acting else accent,
            width=4 if winner or acting else 2,
        )
        fit(d, (x, 80), fighter.name, 29, width=390)
        fit(d, (x, 380), fighter.class_name + f" · Lv {fighter.level}", 25, width=390)
        fit(d, (x, 411), fighter.subclass or fighter.title, 18, color="#bdb6ce", width=390)
        fit(
            d,
            (x, 437),
            f"{fighter.weapon} · {RARITIES[fighter.rarity]}",
            17,
            color=accent,
            width=390,
        )
        fit(d, (x, 459), fighter.affinity_name, 14, color="#bdb6ce", width=390)
        for y, label, current, maximum, tint in (
            (492, "HP", fighter.hp, fighter.max_hp, accent),
            (544, "MP", fighter.mp, fighter.max_mp, "#b1a6e3"),
        ):
            d.rounded_rectangle((x - 185, y, x + 185, y + 15), radius=7, fill="#181924")
            fill = 370 * max(0, min(1, current / max(1, maximum)))
            if fill:
                d.rounded_rectangle(
                    (x - 185, y, x - 185 + max(15, fill), y + 15),
                    radius=7,
                    fill="#e2939b" if label == "HP" and current < maximum * 0.25 else tint,
                )
            fit(d, (x, y - 13), f"{label}  {current} / {maximum}", 15, width=380)
        statuses = list(fighter.statuses)
        if fighter.shield:
            statuses.insert(0, f"Shield {fighter.shield}")
        fit(
            d,
            (x, 590),
            (
                "WON"
                if winner
                else (
                    "LOST"
                    if defeated
                    else "DRAW" if state.finished else " · ".join(statuses) or fighter.title
                )
            ),
            36 if state.finished else 17,
            color="#efd493" if winner else "#e9a4ae" if defeated else "#bdb6ce",
            width=390,
        )
    fit(
        d,
        (550, 253),
        "DRAW" if state.finished and state.winner_id is None else "VS",
        130 if intro else 69,
        color="#f7e6fa",
        width=230 if intro else 160,
    )
    fit(
        d,
        (550, 340),
        (
            "VICTORY"
            if state.finished and state.winner_id
            else "CHALLENGE" if intro else f"MOVE {state.moves}"
        ),
        16,
        color="#dac295",
        width=180,
    )
    fit(d, (550, 410), arena.upper(), 16, color=arena_accent, width=175)
    if state.finished:
        fit(d, (550, 460), "SOULS UNBROKEN", 12, color="#bdb6ce", width=165)
    elif not intro:
        actor = state.left if state.last_actor == state.left.user_id else state.right
        fit(d, (550, 460), actor.last_move, 14, color="#f7e6fa", width=175)
    output = BytesIO()
    image.save(output, "PNG")
    data = output.getvalue()
    if len(data) > 4 * 1024 * 1024:
        raise ValueError("Duel card exceeds upload budget")
    return data
