"""Combined dynamic status thumbnail; other encounter content stays native."""

from io import BytesIO
from functools import lru_cache

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from bot.services.card_renderer import font


@lru_cache(maxsize=24)
def _title_font(size):
    for path in ("C:/Windows/Fonts/georgiab.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"):
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return font(size)


@lru_cache(maxsize=8)
def _encounter_base(path, modified_ns):
    """Decode and resize once per approved asset; callers must copy before drawing."""
    with Image.open(path) as source:
        source.draft("RGB", (1024, 1024))
        art = source.convert("RGB")
    # Preserve the full illustration and its aspect ratio at a bounded size.
    height = max(1, round(art.height * 1024 / art.width))
    return art.resize((1024, height), Image.Resampling.LANCZOS).convert("RGBA")


@lru_cache(maxsize=16)
def render_scene_art(path, modified_ns, enemy_name=""):
    """Cache static artwork, optionally with an encounter's unchanging name."""
    art = _encounter_base(path, modified_ns)
    if enemy_name:
        overlay = Image.new("RGBA", art.size)
        shade = ImageDraw.Draw(overlay)
        for y in range(min(art.height, 90)):
            shade.line((0, y, art.width, y), fill=(4, 10, 19, round((1 - y / 90) * 110)))
        # Composite onto a new image: cached base pixels and approved files
        # remain untouched. HP and intent never enter this static cache key.
        art = Image.alpha_composite(art, overlay)
        draw = ImageDraw.Draw(art)
        size = 34
        while size > 20 and draw.textlength(enemy_name, font=_title_font(size)) > 955:
            size -= 1
        draw.text((30, 18), enemy_name, font=_title_font(size), fill="#f2f6ff",
                  stroke_width=1, stroke_fill="#173e58")
        baseline = 34 + size
        draw.line((32, baseline, 400, baseline), fill="#6795af", width=1)
        draw.polygon([(212, baseline - 5), (217, baseline), (212, baseline + 5), (207, baseline)],
                     outline="#a4d7f1")
    output = BytesIO()
    art.convert("RGB").save(output, format="JPEG", quality=85)
    return output.getvalue()


@lru_cache(maxsize=24)
def render_encounter_art(path, modified_ns, name, hp, max_hp, intent, status):
    """Decorate approved art with live enemy data; never alter the source file.

    The timestamp invalidates replaced assets; the immutable base is shared
    between turns so changing HP doesn't decode and resize the artwork again.
    """
    art = _encounter_base(path, modified_ns).copy()
    height = art.height
    overlay = Image.new("RGBA", art.size)
    shade = ImageDraw.Draw(overlay)
    # A light, shallow title scrim leaves the illustration's brightness intact.
    # The opaque HP panel already provides its own contrast at the bottom.
    for y in range(min(height, 116)):
        shade.line((0, y, 1024, y), fill=(4, 10, 19, round((1 - y / 116) * 110)))
    art = Image.alpha_composite(art, overlay)
    draw = ImageDraw.Draw(art)
    size = 34
    while size > 24 and draw.textlength(name, font=_title_font(size)) > 955:
        size -= 1
    draw.text((30, 18), name, font=_title_font(size), fill="#f2f6ff", stroke_width=1, stroke_fill="#173e58")
    title_end = 22 + size + 12
    draw.line((32, title_end, 400, title_end), fill="#6795af", width=1)
    draw.polygon([(212, title_end - 5), (217, title_end), (212, title_end + 5), (207, title_end)], outline="#a4d7f1")
    # Wrap long telegraphs without clipping names or inventing combat details.
    from bot.services.card_renderer import lines
    intent = intent[2:] if intent[:1] in {"◈", "◇", "⚠"} else intent
    cy = title_end + 24
    draw.polygon([(42, cy - 9), (51, cy), (42, cy + 9), (33, cy)], outline="#f5729d", width=2)
    draw.polygon([(42, cy - 3), (45, cy), (42, cy + 3), (39, cy)], fill="#f5729d")
    for index, line in enumerate(lines(draw, intent, 18, 914)):
        draw.text((63, title_end + 12 + index * 23), line, font=font(18), fill="#ffd1dc",
                  stroke_width=1, stroke_fill="#252130")

    top = height - (104 if status else 82)
    draw.rounded_rectangle((18, top, 1006, height - 14), radius=14,
                           fill=(8, 12, 20, 238), outline="#cb5277", width=2)
    # Restrained diamond corners echo the reference's ornamental frame.
    for x in (18, 1006):
        cy = (top + height - 14) // 2
        draw.polygon([(x, cy - 7), (x + 7, cy), (x, cy + 7), (x - 7, cy)], fill="#13131e", outline="#ef7098")
    if status:
        draw.text((38, top + 8), status, font=font(17), fill="#cdb3e9")
    y = height - 62
    draw.text((38, y), "♥", font=font(29), fill="#fa5688")
    current = str(hp)
    draw.text((78, y), current, font=font(28), fill="#ff6895")
    offset = draw.textlength(current, font=font(28))
    draw.text((78 + offset, y), f" / {max_hp}", font=font(28), fill="#f4f1fa")
    x = max(238, round(88 + draw.textlength(f"{hp} / {max_hp}", font=font(28))))
    right, bar_y, bar_h = 979, y + 4, 28
    draw.rounded_rectangle((x, bar_y, right, bar_y + bar_h), radius=14, fill="#242a33", outline="#525664")
    ratio = max(0, min(1, hp / max(1, max_hp)))
    length = round((right - x - 2) * ratio)
    if length:
        fill = Image.new("RGBA", (right - x - 2, bar_h - 2))
        gradient = ImageDraw.Draw(fill)
        for px in range(length):
            t = px / max(1, right - x - 2)
            gradient.line((px, 0, px, bar_h), fill=(255, round(57 + 70 * t), round(105 + 55 * t), 255))
        mask = Image.new("L", fill.size)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, length - 1, bar_h - 3), radius=min(13, length // 2), fill=255)
        art.paste(fill, (x + 1, bar_y + 1), mask)
    output = BytesIO()
    art.convert("RGB").save(output, format="JPEG", quality=85)
    return output.getvalue()


@lru_cache(maxsize=16)
def _enemy_portrait(path):
    with Image.open(path) as image:
        return ImageOps.fit(image.convert("RGB"), (112, 128), method=Image.Resampling.LANCZOS)


def render_status_panel(name, hp, max_hp, portrait, *, mp=None, max_mp=None, effects=()):
    """Return one status panel, without header, battle log, XP or action buttons."""
    image = Image.new("RGB", (900, 195 if mp is not None else 180), "#11151e")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((1, 1, 898, image.height - 2), radius=12, outline="#3d4253", width=2)
    image.paste(ImageOps.fit(portrait, (112, 128), method=Image.Resampling.LANCZOS), (20, 24))

    def text(x, y, value, size=23, color="#eeeaf2", width=728):
        value = str(value)
        while size > 16 and draw.textlength(value, font=font(size)) > width:
            size -= 1
        while value and draw.textlength(value, font=font(size)) > width:
            value = value[:-2] + "…"
        draw.text((x, y), value, font=font(size), fill=color)

    def bar(y, label, current, maximum, color):
        text(154, y - 5, label, 22, color)
        draw.rounded_rectangle((201, y, 653, y + 23), radius=7, fill="#282e3b", outline="#475063")
        fill = round(452 * max(0, min(1, current / max(1, maximum))))
        if fill:
            draw.rounded_rectangle((201, y, 201 + fill, y + 23), radius=min(7, fill // 2), fill=color)
        text(676, y - 6, f"{current} / {maximum}", 23, width=201)

    text(154, 20, name, 27)
    bar(76, "HP", hp, max_hp, "#f27da9" if mp is not None else "#ec566c")
    if mp is not None:
        bar(119, "MP", mp, max_mp, "#8981ef")
    text(154, 158 if mp is not None else 125, " · ".join(effects), 18, "#c6b0f2")
    output = BytesIO()
    image.save(output, format="PNG")
    output.seek(0)
    return output


def render_dungeon_panels(profile, run, asset, avatar, player_name):
    battle = run.state["battle"]

    def effects(fighter):
        result = [f"Shield {fighter['shield']}"] if fighter.get("shield", 0) > 0 else []
        result.extend(f"{key.replace('_', ' ').title()} ({duration})"
                      for key, duration in fighter.get("statuses", {}).items() if duration > 0)
        return result

    enemy = battle["enemy"]
    enemy_panel = render_status_panel(enemy["name"], enemy["hp"], enemy["max_hp"],
                                      _enemy_portrait(str(asset)), effects=effects(enemy))
    player_panel = None
    if avatar:
        with Image.open(BytesIO(avatar)) as image:
            portrait = image.convert("RGB")
        player_panel = render_status_panel(player_name, run.hp, profile.max_hp, portrait,
            mp=run.mp, max_mp=profile.max_mp, effects=effects(battle["player"]))
    if player_panel is None:
        return enemy_panel, False
    with Image.open(enemy_panel) as enemy_image:
        with Image.open(player_panel) as player_image:
            composite = Image.new("RGB", (enemy_image.width, enemy_image.height + player_image.height), "#11151e")
            composite.paste(enemy_image, (0, 0))
            composite.paste(player_image, (0, enemy_image.height))
            output = BytesIO()
            composite.save(output, format="PNG")
    enemy_panel.close()
    player_panel.close()
    output.seek(0)
    return output, True
