"""Combined dynamic status thumbnail; other encounter content stays native."""

from io import BytesIO
from functools import lru_cache

from PIL import Image, ImageDraw, ImageOps

from bot.services.card_renderer import font


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
