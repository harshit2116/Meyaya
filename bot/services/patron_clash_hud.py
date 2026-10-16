"""Single-message Origin/Erasure spectacle; no combat mutations or live rendering."""
import asyncio
from functools import lru_cache
from io import BytesIO
from pathlib import Path

import discord

from bot.services.veyra_boss_hud import safe
from bot.services.patron_clash_dialogue import dialogue_for
from bot.utils.image_work import animation_work

ASSETS = Path(__file__).resolve().parents[1] / "assets/duels"
DELIVERY_SECONDS = 6
ATTACKS = {
    "Prism Cascade": ("cascade", "Five flowering rays cross the fractured sky."),
    "World Sever": ("sever", "Mournfang cuts through the world's protection."),
    "Genesis Crown": ("genesis", "Everbloom crowns the fragments of a broken reality."),
    "Abyss Dominion": ("dominion", "The empty horizon answers Veyra."),
    "Origin Protocol · The First Dawn": ("dawn", "A beginning blooms where the ending should have been."),
    "Enemy of All · Absolute Erasure": ("erasure", "The last boundary between the world and absence breaks."),
}
PHASES = ("THE FIRST FRACTURE", "REALITY UNRAVELS", "THE LAST POSSIBLE WORLD")


def phase_for(state):
    return max(0, min(2, state.memory_count - 1))


def actor_for(state):
    return next((f for f in (state.left, state.right) if f.user_id == state.last_actor), None)


def scene_for(state, *, intro=False, final=False, exchange=False):
    if exchange:
        actor = actor_for(state)
        return ATTACKS.get(actor.last_move, ("worldfall", ""))[0] if actor and state.finisher else "worldfall"
    if final or state.finished:
        return ("origin-win" if state.winner_id == state.left.user_id else
                "erasure-win" if state.winner_id == state.right.user_id else "worldfall")
    if intro:
        return "opening"
    actor = actor_for(state)
    if actor and actor.last_move in ATTACKS:
        return ATTACKS[actor.last_move][0]
    return "worldfall" if phase_for(state) else "arena"


@lru_cache(maxsize=24)
def media_bytes(scene, animated):
    if scene == "opening" and not animated:
        scene = "arena"
    suffix = "gif" if animated else "jpg"
    path = ASSETS / f"clash-{scene}-v3.{suffix}"
    if path.stat().st_size > 7_000_000:
        raise ValueError("Clash media exceeds upload budget")
    return path.read_bytes(), path.name


def chronicle_layout(state, history=None):
    view = discord.ui.LayoutView(timeout=None)
    lines = ["# Worldfall chronicle"] + [safe(line) for line in (state.history if history is None else history)]
    chunk = ""
    for line in lines:
        if len(chunk) + len(line) + 1 > 3500:
            view.add_item(discord.ui.TextDisplay(chunk))
            chunk = ""
        chunk += line + "\n"
    if chunk:
        view.add_item(discord.ui.TextDisplay(chunk))
    return view


def battle_layout(state, *, media=None, intro=False, final=False, exchange=False, history_note="", controller=None):
    ended = (final or state.finished) and not exchange
    phase = phase_for(state)
    title = "ORIGIN // ERASURE" if intro else PHASES[phase]
    accent = (0xC4A7EE, 0xD98BBE, 0xFF617E)[phase]
    if ended:
        title = ("THE FIRST DAWN RETURNS" if state.winner_id == state.left.user_id else
                 "THE LAST BLOOM GOES SILENT" if state.winner_id == state.right.user_id else
                 "A WORLD WITHOUT A VERDICT")
        accent = 0xF3B2DC if state.winner_id == state.left.user_id else 0xDC345F
    elif exchange:
        title = "THE FINAL EXCHANGE" if state.finisher else "THE WORLD HOLDS ITS BREATH"
    progress = " · ".join(("◆ " if i == phase else "◇ ") + str(i+1) for i in range(3))
    items = [discord.ui.TextDisplay(
        f"-# WORLDFALL / TWO AUTHORITIES. ONE WORLD.\n# {title}\n"
        + ("**Meyaya · Bloom of Origin** ⚔ **Veyra · Enemy of All**" if intro else
           f"-# ACT {phase+1}/3  {progress} · Move {state.moves} · Round {state.round}"))]
    if media:
        items.append(discord.ui.MediaGallery(discord.MediaGalleryItem(
            media=media, description="Meyaya's prismatic Origin meets Veyra's crimson Erasure.")))
    if intro:
        items.append(discord.ui.TextDisplay(
            "> **Meyaya:** Every ending still belongs to a story.\n"
            "> **Veyra:** Then I will erase the author."))
    else:
        actor = actor_for(state)
        if actor:
            text = ATTACKS.get(actor.last_move, ("", ""))[1]
            items.append(discord.ui.TextDisplay(
                f"### {'✦' if actor is state.left else '◇'} {safe(actor.last_move)}\n"
                f"**{safe(actor.name)}** · {text}"))
    items.append(discord.ui.Separator())
    for fighter, identity, motif in (
        (state.left, "MEYAYA / ORIGIN", "Everbloom · Prismatic authority"),
        (state.right, "VEYRA / ERASURE", "Mournfang · Hostile authority"),
    ):
        items.append(discord.ui.TextDisplay(
            f"### {identity}\n{motif}\nHP **UNKNOWN** · MP **UNKNOWN**\n"
            f"-# Signatures released: {fighter.skills_used} · "
            f"{'Acting' if not ended and not exchange and state.last_actor == fighter.user_id else 'Authority present'}"))
    dialogue = dialogue_for(state, final=ended, exchange=exchange)
    if dialogue and not intro:
        first, line, second, reply = dialogue
        items.append(discord.ui.TextDisplay(
            f"> **{first}:** {safe(line)}\n> **{second}:** {safe(reply)}"))
    elif state.dialogue and not intro and not ended:
        items.append(discord.ui.TextDisplay(f"> {safe(state.dialogue)}"))
    items.append(discord.ui.Separator())
    if ended:
        line = ("**Origin prevails.** “I can begin again.”" if state.winner_id == state.left.user_id else
                "**Erasure prevails.** “No author. No ending. Only me.”" if state.winner_id == state.right.user_id else
                "**Neither authority yields.** Reality pays the price.")
        items.append(discord.ui.TextDisplay(
            f"### Worldfall verdict\n{line}\n{safe(state.verdict)}\n"
            f"Finisher: **{safe(state.finisher or 'Worldfall verdict')}**"))
    record = ("The last light meets the last silence. The verdict follows." if exchange else
              "\n".join("› " + safe(line) for line in state.history[-3:]) or "The two authorities enter the same sky.")
    items.append(discord.ui.TextDisplay("### Battle record\n" + record))
    if history_note:
        items.append(discord.ui.TextDisplay(history_note))
    items.append(discord.ui.TextDisplay("-# Automatic cinematic clash · Temporary encounter · Saved souls unchanged"))
    view = ClashControls(controller, ended or exchange, exchange=exchange) if controller else discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.Container(*items, accent_colour=accent))
    if controller:
        view.add_controls()
    return view


class ClashControls(discord.ui.LayoutView):
    def __init__(self, controller, ended, *, exchange=False):
        super().__init__(timeout=180)
        self.controller, self.ended = controller, ended
        self.exchange = exchange

    def add_controls(self):
        hud = self.controller
        motion = discord.ui.Button(
            label="Use static artwork" if hud.motion else "Enable cinematics",
            style=discord.ButtonStyle.secondary, disabled=self.ended)
        record = discord.ui.Button(label="Battle chronicle", style=discord.ButtonStyle.secondary, emoji="📜", disabled=self.exchange)
        motion.callback = self.toggle_motion
        record.callback = self.chronicle
        self.add_item(discord.ui.ActionRow(motion, record))

    async def toggle_motion(self, interaction):
        hud = self.controller
        if interaction.user.id != hud.owner_view.owner:
            await interaction.response.send_message("Only the person who started this clash can change its presentation.", ephemeral=True)
            return
        await interaction.response.defer()
        async with hud.lock:
            if hud.current_view is not self or hud.final or hud.owner_view.closed:
                return
            hud.motion = not hud.motion
            await hud._update(hud.engine, intro=hud.intro, final=hud.final, history_note=hud.history_note)

    async def chronicle(self, interaction):
        if self.controller.exchange:
            await interaction.response.send_message("The final exchange is playing. The chronicle returns with the verdict.", ephemeral=True)
            return
        await interaction.response.send_message(
            view=chronicle_layout(self.controller.engine.state, self.controller.history), ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none())

    async def on_timeout(self):
        hud = self.controller
        async with hud.lock:
            if hud.current_view is not self:
                return
            for child in self.walk_children():
                if isinstance(child, discord.ui.Button):
                    child.disabled = True
            try:
                async with asyncio.timeout(DELIVERY_SECONDS):
                    await hud.message.edit(view=self)
            except (discord.HTTPException, TimeoutError):
                pass

    async def on_error(self, interaction, error, item):
        self.controller.cog.report(error, "clash_controls")
        sender = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
        await sender("The presentation control could not update. The battle continues.", ephemeral=True)


class PatronClashHud:
    def __init__(self, cog, owner_view, channel):
        self.cog, self.owner_view, self.channel = cog, owner_view, channel
        self.message = None
        self.media_key = None
        self.motion = True
        self.art_failed = False
        self.current_view = None
        self.lock = asyncio.Lock()
        self.engine = None
        self.intro = self.final = False
        self.history_note = ""
        self.hold_seconds = 1.5
        self.seen = set()
        self.move_number = -1
        self.move_scene = None
        self.exchange = False
        self.history = []
        self.recorded_move = 0

    async def update(self, engine, **kwargs):
        async with self.lock:
            return await self._update(engine, **kwargs)

    async def _update(self, engine, *, intro=False, final=False, exchange=False, history_note=""):
        self.engine, self.intro, self.final, self.history_note = engine, intro, final or engine.state.finished, history_note
        self.exchange = exchange
        if engine.state.moves > self.recorded_move:
            self.history = (self.history + list(engine.state.log))[-100:]
            self.recorded_move = engine.state.moves
        if self.message is None:
            self.message = getattr(self.owner_view, "message", None)
        scene = scene_for(engine.state, intro=intro, final=final, exchange=exchange)
        if not intro and not self.final:
            if engine.state.moves != self.move_number:
                self.move_scene = scene if scene not in self.seen else (
                    "worldfall" if phase_for(engine.state) else "arena"
                )
                self.move_number = engine.state.moves
            scene = self.move_scene
        animated = self.motion and (scene == "opening" or scene in {v[0] for v in ATTACKS.values()})
        key = (scene, animated)
        self.hold_seconds = 10.5 if intro and animated else 2.7 if animated and scene not in self.seen else 1.5
        if exchange:
            self.hold_seconds = 2.8 if self.motion else 1.2
        self.seen.add(scene)
        attachments = list(getattr(self.message, "attachments", ())) if self.message else []
        media = f"attachment://{attachments[0].filename}" if attachments else None
        if key != self.media_key and not self.art_failed:
            try:
                data, name = await animation_work(media_bytes, *key)
                attachments = [discord.File(BytesIO(data), filename=name)]
                media = f"attachment://{name}"
            except Exception as error:
                self.cog.report(error, "clash_art")
                # Do not leave a previous attack's artwork under the new attack label.
                attachments, media = [], None
                self.art_failed = True
        if self.art_failed:
            attachments, media = [], None
            self.hold_seconds = 1.2 if exchange else 1.5

        async def deliver(layout, files):
            if self.message is None:
                return await self.channel.send(view=layout, files=files, allowed_mentions=discord.AllowedMentions.none())
            return await self.message.edit(view=layout, attachments=files, allowed_mentions=discord.AllowedMentions.none())

        layout = battle_layout(engine.state, media=media, intro=intro, final=final, exchange=exchange,
                               history_note=history_note, controller=self)
        try:
            async with asyncio.timeout(DELIVERY_SECONDS):
                message = await deliver(layout, attachments)
        except (discord.HTTPException, TimeoutError) as error:
            layout.stop()
            self.cog.report(error, "clash_delivery")
            if not media:
                raise
            self.art_failed = True
            self.hold_seconds = 1.2 if exchange else 1.5
            layout = battle_layout(engine.state, intro=intro, final=final, exchange=exchange,
                                   history_note=history_note, controller=self)
            async with asyncio.timeout(DELIVERY_SECONDS):
                message = await deliver(layout, [])
        if self.current_view:
            self.current_view.stop()
        self.current_view = layout
        self.message, self.media_key = message, key
        self.owner_view.message = message
        return message

    def close_if_interrupted(self):
        if self.current_view:
            self.current_view.stop()
            self.current_view = None

