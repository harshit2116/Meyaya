"""Meyaya's native bossfight presentation; all combat state remains engine-owned."""

from functools import lru_cache
from io import BytesIO

import discord
from PIL import Image, ImageDraw, ImageOps

from bot.services.meyaya_boss_renderer import template
from bot.services.veyra_boss_hud import safe

ASSET_PREFIX = "meyaya"
STAGES = (
    ("I · DIVINE PRESENCE", "SOUL INTERFACE / ORIGIN PROTOCOL", 0xF3B2DC),
    ("II · SPELL MEMORY", "SOUL INTERFACE / PATTERN RECOGNIZED", 0xC4A7EE),
    ("III · PRISM CASCADE", "SOUL INTERFACE / PRISMATIC RESONANCE", 0xA8ECEC),
)


def stage_for(engine):
    return 2 if engine.boss.skills_used or engine.reflected else 1 if engine.state.memory_count else 0


def signature_for(engine):
    return engine.boss.last_move == "Prism Cascade" or engine.boss.last_move.startswith("Prism Reflection")


def warning_for(engine):
    if engine.state.finished:
        return "Combat ended."
    action = engine.boss_actions + 1
    if engine.learned_signature and not engine.reflected and action >= 3 and engine.boss.mp >= 18:
        return f"PRISM REFLECTION · next Meyaya action\nA single reflection of **{safe(engine.learned_signature)}** is prepared."
    if action in {2, 4} and engine.boss.mp >= (16 if engine.pattern == "magic" else 22):
        return f"PRISM CASCADE · next Meyaya action\nFive flowering rays · **{safe(engine.ray_affinity.title())}** affinity."
    return "EVERBLOOM · next Meyaya action\nCrystal Petals · Combat resolves automatically."


@lru_cache(maxsize=8)
def stage_art(stage, cinematic=False, opening=False):
    scene = "victory" if stage == 4 else "opening" if opening else "battle"
    base = ImageOps.pad(template(f"meyaya-{scene}-v3.png"), (960, 420), color=(27, 18, 35)).convert("RGB")
    frames = []
    for tick in range(8 if cinematic else 1):
        frame = base.copy()
        if cinematic:
            draw = ImageDraw.Draw(frame, "RGBA")
            # Small drifting petals at the edges, without obscuring the character.
            for index in range(12):
                x = 14 + index * 77
                y = 365 + (index * 9 + tick * 5) % 40
                draw.ellipse((x, y, x + 10, y + 5), fill=(225, 145, 205, 210))
        frames.append(frame)
    output = BytesIO()
    if cinematic:
        palette = base.resize((640, 280)).quantize(colors=96)
        small = [frame.resize((640, 280)).quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
        small[0].save(output, "GIF", save_all=True, append_images=small[1:], duration=180, loop=1)
        for frame in small:
            frame.close()
        palette.close()
    else:
        frames[0].save(output, "JPEG", quality=85)
    base.close()
    for frame in frames:
        frame.close()
    return output.getvalue()


def battle_layout(engine, *, media=None, guardian="", final=False, history_note=""):
    state, player, boss = engine.state, engine.player, engine.boss
    title, interface, color = STAGES[stage_for(engine)]
    if final:
        title = ("A SOUL BEYOND EXPECTATION" if state.winner_id == player.user_id else
                 "THE BLOOM REMAINS" if state.winner_id == boss.user_id else "AN UNFINISHED BLOOM")
    items = [discord.ui.TextDisplay(
        f"-# {interface}\n# {title}\n**Meyaya · Bloom of Origin**\n"
        f"-# Move {state.moves} · Round {state.round} · Automatic battle")]
    if media:
        items.append(discord.ui.MediaGallery(discord.MediaGalleryItem(media=media)))
    items.append(discord.ui.TextDisplay(
        f"### Everbloom / {safe(state.boss_form)}\nHP **??? / ???** · MP **??? / ???**\n"
        f"Spell Memory **{state.memory_count}/3** · Potential **BEYOND MEASUREMENT**\n"
        f"-# {safe(state.counter_pattern)}"))
    items.append(discord.ui.Separator())
    statuses = " · ".join(f"{safe(key.replace('_', ' ').title())} ({value})" for key, value in player.statuses.items())
    items.append(discord.ui.TextDisplay(
        f"### {safe(player.name)}\n{safe(player.class_name)} · Soul Level {player.level}\n"
        f"HP **{player.hp}/{player.max_hp}** · MP **{player.mp}/{player.max_mp}** · Shield **{player.shield}**\n"
        f"{safe(player.weapon)}" + (f"\n{statuses}" if statuses else "") +
        (f"\n-# Companion: {safe(guardian)}" if guardian else "")))
    if not final:
        items.append(discord.ui.TextDisplay(f"### ◇ Threat forecast\n{warning_for(engine)}"))
        dialogue = state.dialogue or (
            f"Keep {guardian} close. I want both of you to remember this." if guardian else
            "Show me what makes your soul different.")
        items.append(discord.ui.TextDisplay(f"> {safe(dialogue)}"))
    else:
        ending = ("Meyaya smiles. Your soul has surprised the Bloom of Origin." if state.winner_id == player.user_id else
                  "The petals settle. Your saved awakening remains untouched." if state.winner_id == boss.user_id else
                  "The bloom waits. Neither soul has the final word.")
        items.append(discord.ui.TextDisplay(
            f"### Aftermath\n{ending}\n{safe(state.verdict)}\n"
            f"Finisher: **{safe(state.finisher or 'None')}**\n"
            f"Damage received **{player.damage_taken}** · Dodges **{player.dodges}** · Signatures **{player.skills_used}**"))
    items.append(discord.ui.Separator())
    record = "\n".join(f"› {safe(line)}" for line in state.history[-3:]) or "The Soul Interface is recording the encounter."
    items.append(discord.ui.TextDisplay("### Battle record\n" + record))
    if history_note:
        items.append(discord.ui.TextDisplay(history_note))
    items.append(discord.ui.TextDisplay("-# Bossfight presentation trial · Temporary combat · Saved progression unchanged"))
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.Container(*items, accent_colour=color))
    return view

