"""Native V2 spectator HUD for the /bossfight Veyra presentation trial."""

from functools import lru_cache
from io import BytesIO
import asyncio
import sys

import discord
from PIL import Image, ImageDraw, ImageOps

from bot.services.meyaya_boss_renderer import template
from bot.utils.image_work import animation_work

STAGES = (
    ("I · HOSTILE PRESENCE", "SOUL INTERFACE / CONNECTION CONTESTED", 0xB93E72),
    ("II · ABYSS MEMORY", "SOUL INTERFACE / MEMORY COMPROMISED", 0xAB64D9),
    ("III · WORLD SEVER", "S O U L  / /  SIGNAL FRACTURED", 0xEF3157),
)
DELIVERY_SECONDS = 6
ASSET_PREFIX = "veyra"


def signature_for(engine):
    return engine.boss.last_move == "World Sever"


def safe(value):
    return discord.utils.escape_markdown(discord.utils.escape_mentions(str(value)))[:240]


def stage_for(engine):
    # Presentation milestones reflect existing mechanics, not invented HP gates.
    return 2 if engine.boss.skills_used else 1 if engine.abyss_marks >= 2 else 0


def warning_for(engine):
    if engine.state.finished:
        return "Combat ended."
    if (engine.boss_actions + 1) % 3 == 0 and engine.boss.mp >= 24:
        return "WORLD SEVER · next Veyra action\nReduces your current shield to 35% and removes resistance. Dodge is resolved automatically."
    return "MOURNFANG · next Veyra action\nSilent Ruin grows stronger as Abyss Memory builds. Combat resolves automatically."


@lru_cache(maxsize=8)
def stage_art(stage, cinematic=False, opening=False):
    """Cache cosmetic art only. No HP, move numbers or player data are baked in."""
    scene = "victory" if stage == 4 else "opening" if opening else "battle"
    source = template(f"veyra-{scene}-v3.png")
    # Wide originals preserve the complete composition; never crop a portrait card.
    base = ImageOps.pad(source, (960, 420), color=(9, 5, 16)).convert("RGB")
    frames = []
    accent = STAGES[min(stage, 2)][2] if stage != 3 else 0xD8B8FF
    color = ((accent >> 16) & 255, (accent >> 8) & 255, accent & 255)
    for tick in range(8 if cinematic else 1):
        frame = base.copy()
        draw = ImageDraw.Draw(frame, "RGBA")
        # Sparse fractures at the edges; never flash the whole screen.
        for index in range(min(stage, 2) * 3 + (4 if cinematic else 0)):
            y = (index * 59 + tick * 17) % 345
            draw.line([(0, y), (65, y + 9), (120 + tick * 8, y - 7)], fill=(*color, 150), width=2)
            draw.line([(960, y + 20), (903, y + 31), (850, y + 15)], fill=(*color, 150), width=2)
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
    stage = stage_for(engine)
    title, interface, color = STAGES[stage]
    if final:
        title = ("AN IMPOSSIBLE SURVIVOR" if state.winner_id == player.user_id else
                 "THE LAST SILENCE" if state.winner_id == boss.user_id else "AN UNWRITTEN ENDING")
    items = [discord.ui.TextDisplay(f"-# {interface}\n# {title}\n**Veyra · Enemy of All**\n-# Move {state.moves} · Round {state.round} · Automatic battle")]
    if media:
        items.append(discord.ui.MediaGallery(discord.MediaGalleryItem(media=media)))
    items.append(discord.ui.TextDisplay(
        f"### Mournfang / Void Revenant\nHP **??? / ???** · MP **??? / ???**\n"
        f"Abyss Memory **{engine.abyss_marks}/3** · Soul pressure **UNREADABLE**"))
    items.append(discord.ui.Separator())
    statuses = " · ".join(f"{safe(key.replace('_', ' ').title())} ({value})" for key, value in player.statuses.items())
    items.append(discord.ui.TextDisplay(
        f"### {safe(player.name)}\n{safe(player.class_name)} · Soul Level {player.level}\n"
        f"HP **{player.hp}/{player.max_hp}** · MP **{player.mp}/{player.max_mp}** · Shield **{player.shield}**\n"
        f"{safe(player.weapon)}" + (f"\n{statuses}" if statuses else "") +
        (f"\n-# Companion: {safe(guardian)}" if guardian else "")))
    if not final:
        items.append(discord.ui.TextDisplay(f"### ◇ Threat forecast\n{warning_for(engine)}"))
        if state.dialogue:
            dialogue = state.dialogue
        elif stage == 2:
            dialogue = f"Raise {player.weapon}. I want you to hear the silence after it."
        elif stage == 1 and guardian:
            dialogue = f"Keep {guardian} close. Witnesses should remember what happens here."
        elif player.alignment == "meyaya":
            dialogue = "She promised you another beginning. I intend to test that promise."
        elif player.alignment == "veyra":
            dialogue = "You carry my mark. Do not mistake recognition for mercy."
        else:
            dialogue = "I remember the shape of every soul that stands here."
        items.append(discord.ui.TextDisplay(f"> {safe(dialogue)}"))
    else:
        ending = ("Veyra lowers Mournfang. For once, the silence hesitates." if state.winner_id == player.user_id else
                  "Your soul falls silent. Your saved awakening remains untouched." if state.winner_id == boss.user_id else
                  "Neither soul disappears. The world has no verdict for you.")
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


class VeyraBossHud:
    def __init__(self, cog, owner_view, channel, guardian="", *, presentation=None):
        self.cog, self.owner_view, self.channel = cog, owner_view, channel
        self.guardian = guardian
        self.message = None
        self.media_key = None
        self.signature_shown = False
        self.art_failed = False
        self.presentation = presentation or sys.modules[__name__]

    async def update(self, engine, *, intro=False, final=False, history_note=""):
        state = engine.state
        presentation = self.presentation
        if self.message is None:
            self.message = getattr(self.owner_view, "message", None)
        signature = (not final and not self.signature_shown and state.last_actor == state.right.user_id
                     and presentation.signature_for(engine))
        if signature:
            self.signature_shown = True
        art_stage = presentation.stage_for(engine)
        if final:
            art_stage = 3 if state.winner_id == state.left.user_id else 4 if state.winner_id == state.right.user_id else 5
        key = (art_stage, bool(signature), bool(intro and not final))
        attachments = list(getattr(self.message, "attachments", ())) if self.message else []
        media = f"attachment://{attachments[0].filename}" if attachments else None
        if key != self.media_key and not self.art_failed:
            try:
                data = await animation_work(presentation.stage_art, *key)
                name = f"{presentation.ASSET_PREFIX}-signature.gif" if signature else f"{presentation.ASSET_PREFIX}-stage.jpg"
                attachments = [discord.File(BytesIO(data), filename=name)]
                media = f"attachment://{name}"
            except Exception as error:
                self.cog.report(error, f"{presentation.ASSET_PREFIX}_hud_art")
                self.art_failed = True
        layout = presentation.battle_layout(engine, media=media, guardian=self.guardian, final=final, history_note=history_note)

        async def deliver(view, files):
            if self.message is None:
                return await self.channel.send(view=view, files=files, allowed_mentions=discord.AllowedMentions.none())
            return await self.message.edit(view=view, attachments=files, allowed_mentions=discord.AllowedMentions.none())

        try:
            async with asyncio.timeout(DELIVERY_SECONDS):
                message = await deliver(layout, attachments)
        except (discord.HTTPException, TimeoutError) as error:
            self.cog.report(error, f"{presentation.ASSET_PREFIX}_hud_delivery")
            if not media:
                raise
            self.art_failed = True
            async with asyncio.timeout(DELIVERY_SECONDS):
                message = await deliver(presentation.battle_layout(engine, guardian=self.guardian, final=final, history_note=history_note), [])
        self.message, self.media_key = message, key
        self.owner_view.message = message
        return message
