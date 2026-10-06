"""Bounded per-move still cards: profile-palette split screen and clash art."""

from io import BytesIO
from pathlib import Path
from functools import lru_cache
import math
from random import Random
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps
from bot.services.card_renderer import font
from bot.services.fantasy_render import portrait, rgb, blend
from bot.data.fantasy import RARITIES

DUEL_SIZE = (1100, 640)
ART_DIR = Path(__file__).resolve().parents[1] / "assets" / "duels"


@lru_cache(maxsize=2)
def cinematic_background(kind):
    with Image.open(ART_DIR / f"{kind}.png") as source:
        return ImageOps.fit(source.convert("L"), DUEL_SIZE, method=Image.Resampling.LANCZOS)


def victory_background(colors):
    image = Image.new("RGB", DUEL_SIZE, (7, 9, 20))
    glow = Image.new("RGB", DUEL_SIZE)
    draw = ImageDraw.Draw(glow)
    for center, color in zip((255, 845), colors):
        draw.ellipse((center - 185, 180, center + 185, 520), fill=blend(color, (0, 0, 0), 0.62))
    image = ImageChops.add(image, glow.filter(ImageFilter.GaussianBlur(85)))
    draw = ImageDraw.Draw(image)
    for offset in range(-5, 6):
        draw.line((550, 380, 550 + offset * 210, 640), fill=(27, 30, 48), width=1)
    for height in (414, 448, 498, 568):
        draw.line((0, height, 1100, height), fill=(27, 30, 48), width=1)
    rng = Random(42)
    for _ in range(100):
        horizontal, vertical = rng.randrange(35, 1065), rng.randrange(170, 493)
        color = blend(colors[int(horizontal > 550)], (15, 18, 32), rng.uniform(0.4, 0.85))
        draw.ellipse((horizontal, vertical, horizontal + 2, vertical + 2), fill=color)
    draw.line((550, 230, 550, 465), fill=(62, 57, 80), width=1)
    return image


def shattered_portrait(image, art, mask, center, color):
    rng = Random(73)
    size = art.width
    points = [
        [
            (
                round(column * size / 4) + (rng.randrange(-16, 17) if 0 < column < 4 else 0),
                round(row * size / 4) + (rng.randrange(-16, 17) if 0 < row < 4 else 0),
            )
            for column in range(5)
        ]
        for row in range(5)
    ]
    for row in range(4):
        for column in range(4):
            top_left, top_right = points[row][column:column + 2]
            bottom_left, bottom_right = points[row + 1][column:column + 2]
            for triangle in ((top_left, top_right, bottom_left), (top_right, bottom_right, bottom_left)):
                shard_mask = Image.new("L", art.size)
                ImageDraw.Draw(shard_mask).polygon(triangle, fill=255)
                shard_mask = ImageChops.multiply(shard_mask, mask)
                bounds = shard_mask.getbbox()
                if bounds is None:
                    continue
                shard = ImageEnhance.Brightness(art).enhance(rng.uniform(0.65, 0.95)).convert("RGBA")
                edge = Image.new("RGBA", art.size)
                ImageDraw.Draw(edge).line((*triangle, triangle[0]), fill=(*color, 180), width=2)
                shard = Image.alpha_composite(shard, edge)
                shard.putalpha(shard_mask)
                shard = shard.crop(bounds)
                shard = shard.rotate(rng.uniform(-13, 13), Image.Resampling.BICUBIC, expand=True)
                midpoint_x = (bounds[0] + bounds[2]) / 2
                midpoint_y = (bounds[1] + bounds[3]) / 2
                spread = rng.uniform(1.14, 1.30)
                position = (
                    round(center[0] + (midpoint_x - size / 2) * spread - shard.width / 2),
                    round(center[1] + (midpoint_y - size / 2) * spread - shard.height / 2),
                )
                image.paste(shard, position, shard)


def cinematic_card(state, portraits, palettes, *, intro):
    """Reusable illustrated backdrops with local, truthful player overlays."""
    colors = [rgb(p[0]) if p else rgb(state.arena[2]) for p in palettes]
    image = Image.new("RGB", DUEL_SIZE)
    fighters = [state.left, state.right]
    if not intro and state.winner_id == state.right.user_id:
        fighters.reverse()
        portraits = tuple(reversed(portraits))
        colors.reverse()
    if intro:
        base = cinematic_background("opening")
        for index in (0, 1):
            toned = ImageOps.colorize(
                base, blend((4, 5, 9), colors[index], 0.10), blend(colors[index], (255, 255, 255), 0.5)
            )
            box = (index * 550, 0, (index + 1) * 550, 640)
            image.paste(toned.crop(box), box)
    else:
        image = victory_background(colors)
    d = ImageDraw.Draw(image)
    # Solid translucent bands retain contrast independently of bright art/palettes.
    overlay = Image.new("RGBA", DUEL_SIZE)
    od = ImageDraw.Draw(overlay)
    od.rectangle((0, 0, 1100, 160), fill=(7, 9, 17, 205))
    od.rectangle((0, 500, 1100, 640), fill=(7, 9, 17, 215))
    image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    d = ImageDraw.Draw(image)
    for index, fighter in enumerate(fighters):
        x = 255 if index == 0 else 845
        art = portrait(portraits[index], fighter.name, 274).convert("RGB")
        loser = not intro and state.winner_id is not None and index == 1
        if loser:
            art = ImageEnhance.Brightness(ImageOps.grayscale(art).convert("RGB")).enhance(0.7)
        mask = Image.new("L", (274, 274))
        ImageDraw.Draw(mask).ellipse((1, 1, 272, 272), fill=255)
        if loser:
            shattered_portrait(image, art, mask, (x, 338), colors[index])
        else:
            image.paste(art, (x - 137, 201), mask)
            d.ellipse((x - 141, 197, x + 141, 479), outline=colors[index], width=5)
        fit(d, (x, 65), fighter.title or fighter.class_name, 27, width=470, color=colors[index])
        fit(d, (x, 111), fighter.name, 38, width=470)
        fit(d, (x, 546), fighter.class_name + f" · Lv {fighter.level}", 22, width=450)
        fit(
            d,
            (x, 594),
            (
                "CHALLENGER"
                if intro and index == 0
                else (
                    "OPPONENT"
                    if intro
                    else "DRAW" if state.winner_id is None else "WON" if index == 0 else "LOST"
                )
            ),
            34,
            width=450,
            color=colors[index],
        )
    if intro:
        fit(d, (550, 322), "VS", 140, width=230)
        fit(d, (550, 455), "SOULS COLLIDE", 17, width=210)
    elif state.winner_id is not None:
        fit(d, (550, 184), "VICTORY", 39, width=270)
        fit(d, (550, 520), state.finisher or "DECISIVE STRIKE", 17, width=260)
    else:
        fit(d, (550, 322), "DRAW", 60, width=230)
    output = BytesIO()
    image.save(output, "PNG")
    if output.tell() > 4 * 1024 * 1024:
        raise ValueError("Duel card exceeds upload budget")
    return output.getvalue()


def fit(draw, pos, text, size=23, color="#f5f0fa", width=370, anchor="mm"):
    text = " ".join(str(text).split())[:150]
    while size > 12 and draw.textlength(text, font=font(size)) > width:
        size -= 1
    while text and draw.textlength(text, font=font(size)) > width:
        text = text[:-2] + "…"
    draw.text(pos, text, font=font(size), fill=color, anchor=anchor)


def render_duel(state, portraits=(b"", b""), palettes=((), ()), *, intro=False):
    if state.right.is_boss:
        from bot.services.meyaya_boss_renderer import render_boss_duel

        return render_boss_duel(state, portraits, palettes, intro=intro)
    if intro or state.finished:
        try:
            return cinematic_card(state, portraits, palettes, intro=intro)
        except (OSError, ValueError):
            # Cosmetic assets must not interrupt combat; keep the existing card fallback.
            pass
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
        statuses = [s.replace("_", " ").title() for s in fighter.statuses]
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
