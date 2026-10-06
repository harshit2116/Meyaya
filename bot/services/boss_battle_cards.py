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
