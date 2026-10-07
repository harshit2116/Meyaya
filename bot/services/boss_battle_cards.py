"""Distinct live arenas and defeated-fighter cards for patron encounters."""

from PIL import Image, ImageDraw, ImageEnhance, ImageOps

from bot.services.fantasy_duel_renderer import fit, shattered_portrait, victory_background
from bot.services.fantasy_render import portrait, rgb
from bot.services.meyaya_boss_renderer import encode, masked_bar, template


def fighter_art(fighter, avatar, size):
    if not fighter.is_boss:
        return portrait(avatar, fighter.name, size).convert("RGB")
    try:
        source = template(f"{fighter.boss_key or 'meyaya'}-profile.png")
        source = source.crop(
            (
                0,
                round(source.height * 0.06),
                round(source.width * 0.63),
                round(source.height * 0.61),
            )
        )
        return ImageOps.fit(source, (size, size), Image.Resampling.LANCZOS, centering=(0.5, 0.25))
    except OSError:
        return portrait(b"", fighter.name, size).convert("RGB")


def fighter_colors(state, palettes):
    return [
        (
            rgb("#ff617e" if fighter.boss_key == "veyra" else "#f3b2dc")
            if fighter.is_boss
            else rgb(palette[0] if palette else "#b6b9ed")
        )
        for fighter, palette in zip((state.left, state.right), palettes)
    ]


def render_boss_arena(state, portraits, palettes):
    if not state.left.is_boss and state.right.boss_key in {"meyaya", "veyra"}:
        return render_meyaya_scene(state, portraits, intro=False)
    colors = fighter_colors(state, palettes)
    image = victory_background(colors)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1100, 115), fill="#0b0914")
    fit(draw, (550, 32), state.boss_form.upper(), 25, width=1040, color="#ffe5f0")
    for index, event in enumerate(state.history[-2:]):
        fit(draw, (550, 70 + index * 26), event, 15, width=1030)
    for index, fighter in enumerate((state.left, state.right)):
        center = 260 if index == 0 else 840
        color = colors[index]
        draw.rounded_rectangle(
            (center - 218, 138, center + 218, 622),
            radius=16,
            fill="#131021",
            outline=color,
            width=2,
        )
        art = fighter_art(fighter, portraits[index], 196)
        mask = Image.new("L", art.size)
        ImageDraw.Draw(mask).ellipse((0, 0, 195, 195), fill=255)
        image.paste(art, (center - 98, 186), mask)
        draw.ellipse((center - 105, 179, center + 105, 389), outline=color, width=3)
        angle = state.moves * 31
        draw.arc(
            (center - 116, 168, center + 116, 400), angle, angle + 235, fill="#eadbfa", width=2
        )
        fit(
            draw,
            (center, 158),
            "AUTHORITY" if fighter.is_boss else "CHALLENGER",
            13,
            width=395,
            color=color,
        )
        fit(draw, (center, 425), fighter.name.upper(), 28, width=395)
        fit(draw, (center, 460), fighter.class_name, 16, width=395, color=color)
        for vertical, label, value, maximum in (
            (515, "HP", fighter.hp, fighter.max_hp),
            (577, "MP", fighter.mp, fighter.max_mp),
        ):
            if fighter.is_boss:
                masked_bar(
                    draw,
                    center - 184,
                    vertical,
                    value,
                    maximum,
                    width=368,
                    label=label,
                    color=color if label == "HP" else "#b69ad9",
                )
            else:
                fit(
                    draw,
                    (center, vertical - 22),
                    f"{label} {value} / {maximum}",
                    17,
                    width=365,
                    color=color,
                )
                draw.rounded_rectangle(
                    (center - 184, vertical, center + 184, vertical + 18), radius=4, fill="#292337"
                )
                extent = round(368 * max(0, min(1, value / max(1, maximum))))
                if extent:
                    draw.rectangle(
                        (center - 184, vertical, center - 184 + extent, vertical + 18), fill=color
                    )
    fit(draw, (550, 226), "MOVE", 16, width=115, color="#c4a7ee")
    fit(draw, (550, 278), f"{state.moves:02}", 55, width=120)
    draw.polygon(((550, 336), (575, 368), (550, 400), (525, 368)), outline="#ffbddb", width=3)
    fit(draw, (550, 450), f"ROUND {state.round}", 13, width=120)
    fit(
        draw,
        (550, 482),
        "WORLD CLASH" if state.left.is_boss else "BOSS FIGHT",
        11,
        width=125,
        color="#ffbddb",
    )
    return encode(image)


def render_boss_defeat(state, portraits, palettes):
    if (
        not state.left.is_boss
        and state.right.boss_key in {"meyaya", "veyra"}
        and state.winner_id == state.right.user_id
    ):
        return render_meyaya_victory(state, portraits)
    colors = fighter_colors(state, palettes)
    fighters = [state.left, state.right]
    portraits = list(portraits)
    if state.winner_id == state.right.user_id:
        fighters.reverse()
        portraits.reverse()
        colors.reverse()
    image = victory_background(colors)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1100, 130), fill="#0b0914")
    draw.rectangle((0, 530, 1100, 640), fill="#0b0914")
    draw_result = state.winner_id is None
    fit(
        draw,
        (550, 45),
        "STALEMATE" if draw_result else "SOUL FRACTURE",
        38,
        width=1010,
        color="#ffe5f0",
    )
    fit(
        draw,
        (550, 95),
        state.verdict if draw_result else f"{fighters[0].name} prevails. {fighters[1].name} falls.",
        20,
        width=1010,
    )
    for index, fighter in enumerate(fighters):
        center = 260 if index == 0 else 840
        art = fighter_art(fighter, portraits[index], 274)
        mask = Image.new("L", art.size)
        ImageDraw.Draw(mask).ellipse((1, 1, 272, 272), fill=255)
        if index == 1 and not draw_result:
            art = ImageEnhance.Brightness(ImageOps.grayscale(art).convert("RGB")).enhance(0.75)
            shattered_portrait(image, art, mask, (center, 327), colors[index])
        else:
            image.paste(art, (center - 137, 190), mask)
            draw.ellipse((center - 143, 184, center + 143, 470), outline=colors[index], width=4)
        fit(draw, (center, 502), fighter.name, 27, width=440)
        fit(
            draw,
            (center, 568),
            "UNBROKEN" if draw_result else "VICTOR" if index == 0 else "DEFEATED",
            27,
            width=440,
            color=colors[index],
        )
    fit(draw, (550, 615), state.finisher or state.verdict, 16, width=1010, color="#c4a7ee")
    return encode(image)


def patron_header(image, state, title, lines=()):
    """Reserve a separate caption strip so artwork and portraits stay unobstructed."""
    erasure = state.right.boss_key == "veyra"
    canvas = Image.new("RGB", (1100, 640), "#140a10" if erasure else "#fff1ed")
    canvas.paste(image.resize((1100, 548), Image.Resampling.LANCZOS), (0, 92))
    draw = ImageDraw.Draw(canvas)
    ink, accent = ("#ffe3e9", "#df4564") if erasure else ("#703044", "#c98a92")
    draw.line((35, 86, 1065, 86), fill=accent, width=1)
    for x in (35, 1065):
        draw.polygon(((x, 80), (x + 5, 86), (x, 91), (x - 5, 86)), fill=accent)
    fit(draw, (550, 20), title, 23, width=1010, color=ink)
    for index, line in enumerate(lines[:2]):
        # The card font has no emoji glyphs; retain the readable battle narration.
        line = "".join(c for c in line if ord(c) < 0x2600 or c.isalnum()).strip()
        fit(draw, (550, 49 + index * 21), line, 14, width=1010, color=ink)
    return encode(canvas)


def scene_portrait(image, fighter, avatar, center, size, bottom=None):
    art = fighter_art(fighter, avatar, size)
    mask = Image.new("L", art.size)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    if bottom is not None:
        start = bottom - (center[1] - size // 2)
        ImageDraw.Draw(mask).rectangle((0, start, size, size), fill=0)
    image.paste(art, (center[0] - size // 2, center[1] - size // 2), mask)


def render_meyaya_scene(state, portraits, *, intro):
    erasure = state.right.boss_key == "veyra"
    key = "veyra" if erasure else "meyaya"
    stage = "encounter" if intro else "arena"
    image = template(f"{key}-{stage}-v2.png").resize((1100, 640), Image.Resampling.LANCZOS)
    centers = (
        (((269, 222), (890, 222)) if intro else ((235, 282), (866, 282)))
        if erasure
        else (((250, 216), (847, 216)) if intro else ((220, 244), (882, 244)))
    )
    scene_portrait(
        image,
        state.left,
        portraits[0],
        centers[0],
        (246 if erasure else 230) if intro else (170 if erasure else 168),
        bottom=None,
    )
    if not intro:
        scene_portrait(image, state.right, portraits[1], centers[1], 170 if erasure else 168)
    draw = ImageDraw.Draw(image)
    for index, fighter in enumerate((state.left, state.right)):
        x = centers[index][0]
        name_y, detail_y = (
            ((394, 446) if intro else (407, 457))
            if erasure
            else ((377, 432) if intro else (346, 387))
        )
        ink = "#ffe5eb" if erasure else "#652b48" if intro else "#fff0f7"
        fit(draw, (x, name_y), fighter.name, 27, width=265, color=ink)
        fit(
            draw,
            (x, detail_y),
            state.boss_form if index else f"{fighter.class_name} · Lv {fighter.level}",
            16,
            width=265,
            color=ink,
        )
        panel = Image.new("RGBA", image.size)
        ImageDraw.Draw(panel).rounded_rectangle(
            (x - 152, 487, x + 152, 610),
            radius=8,
            fill=(18, 8, 14, 195) if erasure else (48, 24, 45, 195),
        )
        image = Image.alpha_composite(image.convert("RGBA"), panel).convert("RGB")
        draw = ImageDraw.Draw(image)
        for y, label, value, maximum in (
            (525, "HP", fighter.hp, fighter.max_hp),
            (577, "MP", fighter.mp, fighter.max_mp),
        ):
            tint = ("#ec5373" if erasure else "#f3b2dc") if label == "HP" else "#c4a7ee"
            if fighter.is_boss:
                masked_bar(draw, x - 132, y, value, maximum, width=264, label=label, color=tint)
            else:
                fit(draw, (x, y - 17), f"{label} {value} / {maximum}", 15, width=264)
                draw.rounded_rectangle((x - 132, y, x + 132, y + 14), radius=4, fill="#342239")
                length = round(264 * max(0, min(1, value / max(1, maximum))))
                if length:
                    draw.rectangle((x - 132, y, x - 132 + length, y + 14), fill=tint)
    draw = ImageDraw.Draw(image)
    badge_y = 330 if erasure else 300
    draw.polygon(
        ((550, badge_y - 40), (599, badge_y), (550, badge_y + 40), (501, badge_y)),
        fill="#260d19" if erasure else "#41213b",
        outline="#dc7e99",
    )
    if intro:
        # Use the encounter renderer's text helper so the existing intro hook remains useful.
        from bot.services import meyaya_boss_renderer

        meyaya_boss_renderer.fit(draw, (550, badge_y), "VS", 43, width=100)
    else:
        fit(draw, (550, badge_y), f"MOVE {state.moves:02}", 19, width=105)
    fit(
        draw,
        (550, 460),
        "AUTHORITY OVERRIDE" if intro else f"ROUND {state.round}",
        13,
        width=210,
        color="#ffd6e0" if erasure else "#652b48",
    )
    return patron_header(
        image,
        state,
        (
            ("VEYRA / ENEMY OF ALL" if erasure else "MEYAYA / BLOOM OF ORIGIN")
            if intro
            else state.boss_form.upper()
        ),
        (state.counter_pattern, state.dialogue) if intro else tuple(state.history[-2:]),
    )


def render_meyaya_victory(state, portraits):
    erasure = state.right.boss_key == "veyra"
    key = "veyra" if erasure else "meyaya"
    image = template(f"{key}-victory-v2.png").resize((1100, 640), Image.Resampling.LANCZOS)
    if erasure:
        scene_portrait(image, state.right, portraits[1], (173, 276), 156)
    art = fighter_art(state.left, portraits[0], 156 if erasure else 208)
    art = ImageEnhance.Brightness(ImageOps.grayscale(art).convert("RGB")).enhance(0.75)
    mask = Image.new("L", art.size)
    ImageDraw.Draw(mask).ellipse((1, 1, art.width - 2, art.height - 2), fill=255)
    plate_y = 360 if erasure else 474
    badges = image.crop((0, plate_y, 1100, 640))
    shattered_portrait(
        image,
        art,
        mask,
        (932, 276) if erasure else (943, 369),
        rgb("#ec5373" if erasure else "#e4acc4"),
    )
    image.paste(badges, (0, plate_y))
    draw = ImageDraw.Draw(image)
    for x, fighter, label in ((173, state.right, "VICTOR"), (932, state.left, "DEFEATED")):
        if erasure:
            fit(draw, (x, 381), fighter.name, 24, width=260, color="#ffe5eb")
            fit(draw, (x, 428), label, 18, width=245, color="#ef8ca1")
        else:
            fit(
                draw,
                (180 if label == "VICTOR" else 943, 574),
                fighter.name,
                23,
                width=280,
                color="#652b48" if label == "VICTOR" else "#fff0f7",
            )
    return patron_header(
        image,
        state,
        "VEYRA PREVAILS / ABSOLUTE ERASURE" if erasure else "MEYAYA PREVAILS / SOUL FRACTURE",
        (
            (
                f"{state.left.name} falls before the Enemy of All."
                if erasure
                else f"{state.left.name} falls before the Bloom of Origin."
            ),
            state.finisher or state.verdict,
        ),
    )
