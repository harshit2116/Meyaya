"""Player-centred duel cut-ins, composed locally from the real Discord avatar."""
from io import BytesIO
import discord
from PIL import Image, ImageDraw, ImageOps

from bot.services.fantasy_render import portrait
from bot.services.fantasy_duel_renderer import fit
from bot.services.meyaya_boss_renderer import template


def safe(value):
    return discord.utils.escape_markdown(discord.utils.escape_mentions(str(value)))[:200]


def render_duel_cut_in(boss_key, avatar, player_name, pose, cinematic=False):
    """No live HP or damage in artwork. Caller caches per encounter, never globally."""
    scene = "opening" if pose == "opening" else "victory" if pose == "defeat" else "battle"
    if cinematic and pose == "boss":
        source = template("clash-origin-v3.png" if boss_key == "meyaya" else "clash-erasure-v3.png")
        # Meyaya's ultimate is left-composed; omit the distant opponent silhouette.
        source = source.crop((0, 0, int(source.width * .65), source.height)) if boss_key == "meyaya" else source.crop(
            (int(source.width * .35), 0, source.width, source.height))
    else:
        source = template(f"{boss_key}-{scene}-v3.png")
        source = source.crop((int(source.width * .35), 0, source.width, source.height))
    boss = ImageOps.fit(source, (510, 350), method=Image.Resampling.LANCZOS)
    square = portrait(avatar, player_name, 510)
    player = ImageOps.fit(square, (510, 350), method=Image.Resampling.LANCZOS)
    base = Image.new("RGB", (960, 420), "#100d1b")
    player_mask = Image.new("L", (510, 350))
    ImageDraw.Draw(player_mask).polygon([(0, 0), (505, 0), (450, 350), (0, 350)], fill=255)
    base.paste(player, (0, 44), player_mask)
    mask = Image.new("L", (510, 350))
    ImageDraw.Draw(mask).polygon([(55, 0), (510, 0), (510, 350), (0, 350)], fill=255)
    base.paste(boss, (450, 44), mask)
    draw = ImageDraw.Draw(base)
    color = "#ff527c" if boss_key == "veyra" else "#efaddd"
    draw.line((454, 394, 509, 44), fill=color, width=4)
    fit(draw, (220, 23), player_name, 24, width=400)
    fit(draw, (735, 23), boss_key.upper(), 24, width=400, color=color)
    active_left = pose in {"player", "victory"}
    active_right = pose in {"boss", "defeat"}
    # Directional edge streaks identify who is acting without inventing a hit.
    for index in range(6):
        y = 300 + index * 14
        if active_left:
            draw.line((0, y, 115 + index * 18, y - 20), fill="#d9baff", width=2)
        if active_right:
            draw.line((960, y, 845 - index * 18, y - 20), fill=color, width=2)
    draw.line((45, 397, 395, 397), fill="#c4a7ee" if active_left else "#393143", width=5)
    draw.line((505, 397, 945, 397), fill=color if active_right else "#393143", width=5)
    label = {"opening": "VS", "player": "YOUR MOVE", "boss": "THEIR MOVE",
             "victory": "VICTORY", "defeat": "DEFEAT", "draw": "DRAW"}[pose]
    draw.polygon([(385, 175), (510, 165), (550, 230), (420, 245)], fill="#170f23")
    fit(draw, (468, 207), label, 21, width=140, color="#fff0fa")
    output = BytesIO()
    if cinematic:
        small = base.resize((720, 315), Image.Resampling.LANCZOS)
        palette = small.quantize(colors=128)
        frames = []
        for tick in range(8):
            frame = small.copy()
            fx = ImageDraw.Draw(frame)
            for index in range(8):
                x = (index * 87 + tick * (14 if active_left else -14)) % 720
                y = 286 + index % 3 * 5
                fx.line((x, y, x + 24, y - 5), fill=color, width=2)
            frames.append(frame.quantize(palette=palette, dither=Image.Dither.NONE))
            frame.close()
        frames[0].save(output, "GIF", save_all=True, append_images=frames[1:], duration=160, loop=1)
        for frame in frames:
            frame.close()
        small.close()
        palette.close()
    else:
        base.save(output, "JPEG", quality=82, optimize=True)
    for image in (base, square, player, player_mask, boss, mask, source):
        image.close()
    return output.getvalue()


def duel_layout(engine, presentation, *, media=None, guardian="", final=False, intro=False, history_note=""):
    state, player, boss = engine.state, engine.player, engine.boss
    stage = presentation.stage_for(engine)
    phase, _, color = presentation.STAGES[stage]
    actor = player if state.last_actor == player.user_id else boss if state.last_actor == boss.user_id else None
    title = "THE CHALLENGE" if intro else f"{safe(actor.name)} · {safe(actor.last_move)}" if actor else "THE DUEL"
    if final:
        title = "YOU DEFIED THE IMPOSSIBLE" if state.winner_id == player.user_id else "THE AUTHORITY REMAINS" if state.winner_id == boss.user_id else "NEITHER SOUL YIELDS"
    items = [discord.ui.TextDisplay(
        f"-# PATRON DUEL / {phase}\n# {title}\n"
        f"**{safe(player.name)}** ⚔ **{safe(boss.name)}**\n"
        f"-# Move {state.moves} · Round {state.round} · Automatic combat")]
    if media:
        items.append(discord.ui.MediaGallery(discord.MediaGalleryItem(
            media=media, description=f"{player.name[:80]}'s Discord avatar facing {boss.name[:80]} in the duel.")))
    if state.history and not intro:
        items.append(discord.ui.TextDisplay("### Latest exchange\n" + "\n".join(
            f"› {safe(line)}" for line in state.history[-3:])))
    items.append(discord.ui.Separator())
    statuses = " · ".join(f"{safe(k.replace('_', ' ').title())} ({v})" for k, v in player.statuses.items())
    items.append(discord.ui.TextDisplay(
        f"### {safe(player.name)} · {safe(player.class_name)}\n"
        f"Soul Level **{player.level}** · HP **{player.hp}/{player.max_hp}** · MP **{player.mp}/{player.max_mp}** · Shield **{player.shield}**\n"
        f"**{safe(player.weapon)}**\n-# Signature: {safe(player.signature_name)}"
        + (f"\n{statuses}" if statuses else "") + (f"\n-# Companion: {safe(guardian)}" if guardian else "")))
    memory = f"Abyss Memory {engine.abyss_marks}/3" if presentation.ASSET_PREFIX == "veyra" else f"Spell Memory {state.memory_count}/3"
    items.append(discord.ui.TextDisplay(
        f"### {safe(boss.name)} · {safe(state.boss_form)}\nHP **??? / ???** · MP **??? / ???**\n-# {memory}"))
    if final:
        items.append(discord.ui.TextDisplay(
            f"### Aftermath\n{safe(state.verdict)}\nFinisher: **{safe(state.finisher or 'None')}**\n"
            f"Damage received **{player.damage_taken}** · Dodges **{player.dodges}** · Signatures **{player.skills_used}**"))
    elif not state.finished:
        items.append(discord.ui.TextDisplay(f"### Threat forecast\n{presentation.warning_for(engine)}"))
        if state.dialogue:
            items.append(discord.ui.TextDisplay(f"> {safe(state.dialogue)}"))
    if history_note:
        items.append(discord.ui.TextDisplay(history_note))
    items.append(discord.ui.TextDisplay("-# Temporary patron duel · Your saved awakening remains unchanged"))
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.Container(*items, accent_colour=color))
    return view
