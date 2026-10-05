"""Local illustrated fantasy creatures and a monster-battle arena."""

from functools import lru_cache
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps
from bot.services.fantasy_duel_renderer import fit
from bot.services.fantasy_render import rgb, blend


@lru_cache(maxsize=4)
def _illustration(species):
    if species not in {"owl", "fox", "dragon", "moth"}:
        raise ValueError("Unknown guardian species")
    path = Path(__file__).resolve().parents[1] / "assets" / "guardians" / f"{species}.png"
    with Image.open(path) as source:
        art = source.convert("RGBA")
    bounds = art.getchannel("A").getbbox()
    if not bounds:
        raise ValueError("Empty guardian illustration")
    art = art.crop(bounds)
    # The fox illustration faces right; normalise the arena's enemy-facing view.
    if species == "fox":
        art = ImageOps.mirror(art)
    art.thumbnail((512, 512), Image.Resampling.LANCZOS)
    return art


def creature(guardian, size=280, *, back=False):
    # The arena mirrors the local portrait to face the other creature.
    # Copy before resizing: the four cached masters are never mutated.
    try:
        art = _illustration(guardian.species).copy()
    except (OSError, ValueError):
        return _fallback_creature(guardian, size, back=back)
    if back:
        art = ImageOps.mirror(art)
    art.thumbnail((size - 12, size - 12), Image.Resampling.LANCZOS)
    alignment = getattr(guardian, "alignment", "")
    if alignment in {"meyaya", "veyra"}:
        # Local material tint; preserve the illustrated anatomy and alpha edges.
        alpha = art.getchannel("A")
        tinted = ImageOps.colorize(
            ImageOps.grayscale(art),
            "#321d35" if alignment == "meyaya" else "#10060f",
            "#ffe3e9" if alignment == "meyaya" else "#eb4266",
        ).convert("RGBA")
        art = Image.blend(art, tinted, 0.45 if alignment == "meyaya" else 0.78)
        art.putalpha(alpha)
    image = Image.new("RGBA", (size, size))
    if alignment:
        draw = ImageDraw.Draw(image)
        colour = "#f7d9aa" if alignment == "meyaya" else "#c52b59"
        draw.ellipse((8, 8, size - 9, size - 9), outline=colour, width=2)
        if alignment == "meyaya":
            draw.ellipse((size // 3, 9, size * 2 // 3, 27), outline=colour, width=3)
        else:
            draw.polygon(
                ((size // 2, 5), (size - 7, size * 3 // 4), (7, size * 3 // 4)),
                outline=colour,
                width=2,
            )
    image.alpha_composite(art, ((size - art.width) // 2, (size - art.height) // 2))
    return image


def _fallback_creature(guardian, size=280, *, back=False):
    image = Image.new("RGBA", (360, 360))
    d = ImageDraw.Draw(image)
    c = rgb(guardian.color)
    light, dark = blend(c, (255, 248, 235), 0.5), blend(c, (25, 20, 43), 0.5)
    # Authored silhouettes per species; rendered at 360 then antialiased.
    if guardian.species == "fox":
        d.polygon(((110, 205), (20, 210), (25, 130), (100, 160)), fill=dark)
        d.ellipse((105, 165, 282, 309), fill=c, outline=dark, width=5)
        d.polygon(
            ((118, 150), (130, 34), (187, 100), (243, 34), (267, 154)),
            fill=c,
            outline=dark,
            width=5,
        )
        d.ellipse((112, 99, 282, 232), fill=c, outline=dark, width=5)
        d.polygon(((120, 170), (196, 210), (274, 170), (227, 230), (164, 230)), fill=light)
    elif guardian.species == "dragon":
        d.polygon(((125, 175), (34, 72), (26, 228), (120, 245)), fill=dark)
        d.polygon(((248, 175), (328, 72), (335, 228), (248, 245)), fill=dark)
        d.ellipse((114, 154, 269, 321), fill=c, outline=dark, width=5)
        d.ellipse((133, 185, 250, 298), fill=light)
        d.polygon(((127, 133), (121, 45), (165, 94), (240, 86), (285, 45), (275, 150)), fill=dark)
        d.ellipse((116, 87, 279, 211), fill=c, outline=dark, width=5)
    elif guardian.species == "owl":
        d.ellipse((57, 140, 161, 290), fill=dark)
        d.ellipse((223, 140, 327, 290), fill=dark)
        d.ellipse((102, 110, 280, 312), fill=c, outline=dark, width=5)
        d.polygon(((109, 136), (101, 60), (162, 112), (239, 110), (286, 60), (277, 146)), fill=c)
        for x in (149, 232):
            d.ellipse((x - 42, 112, x + 42, 197), fill=light)
        d.polygon(((179, 178), (198, 178), (188, 201)), fill="#dfb76b")
    else:
        for bounds in (
            (18, 61, 176, 232),
            (193, 61, 351, 232),
            (38, 210, 178, 318),
            (191, 210, 332, 318),
        ):
            d.ellipse(bounds, fill=c, outline=light, width=5)
        for x in (97, 272):
            d.ellipse((x - 21, 143, x + 21, 185), fill=dark)
        d.ellipse((164, 124, 209, 307), fill=dark)
        d.ellipse((151, 97, 221, 168), fill=light)
        d.line((169, 111, 137, 57), fill=light, width=5)
        d.line((203, 111, 235, 57), fill=light, width=5)
    if not back:
        for x in ((172, 199) if guardian.species == "moth" else (150, 235)):
            d.ellipse((x - 7, 147, x + 7, 169), fill="#221f35")
            d.ellipse((x - 3, 149, x + 1, 154), fill="white")
    else:
        image = ImageOps.mirror(image)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def png(image):
    out = BytesIO()
    image.save(out, "PNG")
    data = out.getvalue()
    if len(data) > 4 * 1024 * 1024:
        raise ValueError("Guardian image exceeds budget")
    return data


def guardian_card(g, owner):
    image = Image.new("RGB", (1000, 660), "#151626")
    d = ImageDraw.Draw(image)
    for y in range(660):
        d.line((0, y, 1000, y), fill=blend((17, 20, 35), rgb(g.color), 0.08 + 0.18 * (1 - y / 660)))
    d.rounded_rectangle((20, 20, 980, 640), radius=24, outline=g.color, width=2)
    fit(d, (500, 53), "MEYAYA / SOUL-BOUND GUARDIAN", 22, width=900)
    art = creature(g, 340)
    image.paste(art, (60, 180), art)
    fit(d, (245, 127), owner, 28, width=375)
    fit(d, (245, 548), g.role, 23, color=g.color, width=375)
    fit(d, (688, 130), g.name, 36, color=g.color, width=520)
    for y, text in (
        (181, f"{g.affinity_name} · Bound to {g.owner_class}"),
        (232, f"HP {g.max_hp}   MP {g.max_mp}   Bond {g.bond}/100"),
        (278, f"ATK {g.attack}   DEF {g.defense}   SPD {g.speed}"),
        (337, g.blessing),
        (375, g.blessing_text),
        (430, f"Trade-off: {g.weakness}"),
        (490, "Strike / Affinity Pulse / Guard / Blessing"),
        (540, "Challenge a member with /guardianbattle"),
    ):
        fit(
            d,
            (690, y),
            text,
            21 if y != 337 else 27,
            color=g.color if y == 337 else "#ece7f6",
            width=510,
        )
    fit(
        d,
        (500, 611),
        "One awakening · one companion · temporary battle resources",
        17,
        color="#bcb5cc",
        width=920,
    )
    return png(image)


def battle_card(battle):
    image = Image.new("RGB", (1000, 660))
    d = ImageDraw.Draw(image)
    for y in range(660):
        d.line((0, y, 1000, y), fill=blend((40, 51, 79), (131, 165, 144), min(1, y / 480)))
    fit(d, (500, 35), f"MEYAYA / GUARDIAN ARENA · MOVE {battle.moves}", 22, width=900)
    for i, (f, position) in enumerate(zip(battle.fighters, ((95, 250), (620, 75)))):
        x, y = position
        d.ellipse((x - 5, y + 240, x + 290, y + 280), fill="#607c76", outline="#a5c4a5", width=3)
        art = creature(f.guardian, 285, back=i == 0)
        if battle.finished and battle.winner_id not in (None, f.guardian.owner_id):
            alpha = art.getchannel("A")
            art = ImageOps.grayscale(art).convert("RGBA")
            art.putalpha(alpha)
        image.paste(art, position, art)
        bx, by = (560, 373) if i == 0 else (35, 84)
        d.rounded_rectangle(
            (bx, by, bx + 400, by + 130),
            radius=18,
            fill="#1c2335",
            outline=f.guardian.color,
            width=2,
        )
        fit(
            d, (bx + 200, by + 27), f"{f.guardian.name} · {f.guardian.affinity_name}", 23, width=370
        )
        fit(
            d,
            (bx + 200, by + 59),
            f"{f.owner_name} · HP {f.hp}/{f.guardian.max_hp} · MP {f.mp}/{f.guardian.max_mp}",
            18,
            width=370,
        )
        d.rounded_rectangle((bx + 20, by + 83, bx + 380, by + 96), radius=6, fill="#343c4c")
        width = int(360 * f.hp / f.guardian.max_hp)
        if width:
            d.rectangle((bx + 20, by + 83, bx + 20 + width, by + 96), fill=f.guardian.color)
        status = (
            "DRAW"
            if battle.finished and battle.winner_id is None
            else (
                ("WON" if battle.winner_id == f.guardian.owner_id else "LOST")
                if battle.finished
                else "WARD READY" if f.guarded else "YOUR TURN" if battle.actor is f else "WAITING"
            )
        )
        fit(d, (bx + 200, by + 113), status, 17, color=f.guardian.color, width=365)
    d.rounded_rectangle((24, 533, 976, 641), radius=18, fill="#182134", outline="#dde5e7", width=2)
    for index, event in enumerate(reversed(battle.history)):
        fit(d, (500, 550 + index * 24), event, 18, width=915)
    fit(
        d,
        (500, 626),
        (
            "Battle complete · fantasy identities unchanged"
            if battle.finished
            else f"{battle.actor.owner_name}, choose your guardian's move below."
        ),
        16,
        width=900,
    )
    return png(image)
