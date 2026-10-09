"""Native Components V2 dungeon screens with owner/revision checked controls."""

import asyncio
import logging
import math
import re
from time import perf_counter
from contextlib import closing
from functools import lru_cache
from dataclasses import dataclass, field
from io import BytesIO

import discord

from bot.data.fantasy_dungeon import ROMAN, campaign_asset, world_for
from bot.data.fantasy_dungeon_lore import lore_scenes, patron_name, lore_asset
from bot.data.fantasy_memory_world import current_scene, ENDING_TITLES, ORIGIN_COLOR
from bot.models.fantasy_dungeon import ACTIVE_PHASES
from bot.services.fantasy_dungeon import DungeonService, DungeonUnavailable, DungeonStale
from bot.services.fantasy_dungeon_combat import enemy_intent
from bot.services.fantasy_dungeon_renderer import render_scene_art
from bot.logging.telemetry import event

logger = logging.getLogger(__name__)
PLAYER_HP = "<:purple_hp:1558053519133642812>"
PLAYER_MP = "<:blue_mp:1558053516902408252>"
EMPTY = "<:empty:1558053073488842752>"
ENEMY_HP = "<:enemy_hp:1558052956379553792>"
BAR_EMOJIS = (PLAYER_HP, PLAYER_MP, EMPTY, ENEMY_HP)
BAR_SEGMENTS = 12


@lru_cache(maxsize=4)
def warn_unavailable_emoji(emoji):
    logger.warning(
        "Dungeon progress emoji %s is missing or unusable in the bot emoji cache; "
        "showing exact numeric vitals without that bar. Check emoji availability/roles "
        "or reload application emojis after uploads.", emoji,
    )


def usable_bar_emojis(bot):
    # Application emojis are loaded by the existing startup hook. Do not make
    # API requests per render. Guild emoji fallback also checks role restrictions.
    application = {emoji.id: emoji for emoji in getattr(bot, "meyaya_application_emojis", ())}
    result = set()
    for markup in BAR_EMOJIS:
        emoji_id = int(markup.rsplit(":", 1)[1][:-1])
        emoji = application.get(emoji_id)
        usable = emoji is not None and emoji.available
        if emoji is None:
            get_emoji = getattr(bot, "get_emoji", None)
            emoji = get_emoji(emoji_id) if get_emoji else None
            usable = emoji is not None and emoji.is_usable()
        if usable:
            result.add(markup)
        else:
            warn_unavailable_emoji(markup)
    return result


def progress_bar(current, maximum, filled_emoji, *, available_emojis=None):
    """Twelve display-only segments; unavailable assets fall back to numbers."""
    if available_emojis is not None and not {filled_emoji, EMPTY} <= available_emojis:
        return ""
    try:
        current, maximum = float(current), float(maximum)
        ratio = min(1, max(0, current / maximum)) if maximum > 0 and math.isfinite(current) and math.isfinite(maximum) else 0
    except (TypeError, ValueError, OverflowError):
        ratio = 0
    filled = max(0, min(BAR_SEGMENTS, round(ratio * BAR_SEGMENTS)))
    return filled_emoji * filled + EMPTY * (BAR_SEGMENTS - filled)


@dataclass
class DungeonScreen:
    title: str | None = None
    description: str | None = None
    color: int = 0x9383BE
    fields: list[tuple[str, str]] = field(default_factory=list)
    footer: str = ""


def vitality(label, current, maximum, *, filled_emoji=ENEMY_HP, available_emojis=None):
    bar = progress_bar(current, maximum, filled_emoji, available_emojis=available_emojis)
    # Separate values from the unspaced strip; subtext keeps inline custom
    # emojis compact rather than rendering an emoji-only jumbo line.
    return f"{label} **{current:,} / {maximum:,}**" + (f"\n-# {bar}" if bar else "")


def effects(fighter):
    values = [f"Shield {fighter['shield']}"] if fighter.get("shield", 0) > 0 else []
    values.extend(f"{key.replace('_', ' ').title()} ({duration})"
                  for key, duration in fighter.get("statuses", {}).items() if duration > 0)
    return " · ".join(f"`{value.upper()}`" for value in values)


def intent_caption(run, battle):
    """Style the engine's telegraph without duplicating its decision rules."""
    intent = enemy_intent(run.floor, run.encounter, battle)
    intent = intent.removeprefix(battle["enemy"]["name"] + " prepares ").removesuffix(".")
    move, _, detail = intent.rpartition(" (")
    if not move:
        return f"◈ {intent}"
    detail = detail.removesuffix(")")
    icon = "◇" if detail in {"raise a shield", "restore HP"} else "⚠" if "stronger" in detail or "drain" in detail else "◈"
    return f"{icon} Preparing **{move}** · {detail[0].upper() + detail[1:]}"


def recent_battle_log(events, *, enemy_name=None):
    """Keep saved events untouched; only the last three distinct lines appear."""
    recent = []
    for event in events:
        event = event.strip()
        if event and (not recent or event != recent[-1]):
            recent.append(event)
    lines = []
    for event in recent[-3:]:
        if enemy_name:
            # Drop the repeated epithet only in displayed log lines. Keep the
            # full identity in the artwork, battle state and persisted history.
            event = event.replace(enemy_name, enemy_name.partition(" · ")[0])
        # Preserve event wording and numbers; emphasize outcomes, not arithmetic.
        event = re.sub(r"\b(?:\d+ damage|No damage|DODGE|CRITICAL)\b", r"**\g<0>**", event)
        if event[:1].isalnum():
            icon = "🛡" if event.startswith("You guard") else "💧" if "MP" in event else "⚔" if "damage" in event else "✧"
            event = icon + " " + event
        lines.append(event)
    return "\n".join(lines)[-1000:] or "-# Choose your opening move."


def dungeon_notice(text):
    view = discord.ui.LayoutView(timeout=180)
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay("### THE TENFOLD DESCENT\n" + text),
        accent_color=0x9383BE,
    ))
    return view


def dungeon_presentation(profile, run, *, available_emojis=None):
    """Pure presentation; no hidden clue flags sent before their story scene."""
    if run is None or run.phase == "abandoned":
        world = world_for(min(10, profile.weapon_level + 1))
        return DungeonScreen("✦ THE TENFOLD DESCENT", "Ten worlds.\nTen guardians.\nOne path.\n\nSomething is waiting at the end.\n\nYour soul's progress survives every failed run.", color=world.color), world.asset()
    world = world_for(run.floor)
    title = "THE SEAL" if run.floor == 10 else f"{world.name} · {ROMAN[run.floor]}"
    asset = world.asset()
    phase = run.phase
    cinematic = run.state.get("sequence") == "opening" or phase == "seal"
    if phase == "complete" and getattr(profile, "ending_route", None):
        if profile.ending_route == "veyra":
            return DungeonScreen(color=0x000000), campaign_asset("cinematic/black")
        return DungeonScreen(ENDING_TITLES[profile.ending_route],
            "A new universe continues. Meyaya, Veyra, and the Witness are gone.\n\n"
            "Your permanent worldline is recorded in `/fantasyprofile`.", color=ORIGIN_COLOR), campaign_asset("cinematic/world-continues")
    if cinematic:
        scene = current_scene(run, profile)
        title, text, asset = scene.title, scene.dialogue, campaign_asset(scene.asset)
    elif phase in {"intro", "story"}:
        scenes = lore_scenes(world, phase, profile.alignment, run.state.get("story_beat", 1))
        scene_title, text = scenes[run.state.get("lore_scene", 0)]
        title += f" · {scene_title}"
        relative = lore_asset(world, phase, run.state.get("story_beat", 1), run.state.get("lore_scene", 0))
        if relative:
            asset = campaign_asset(relative)
    elif phase == "boss_intro":
        title = f"GUARDIAN · {world.boss.name}"
        text = world.narrative("boss_intro", profile.alignment)
        asset = world.asset("boss")
    elif phase == "combat":
        battle = run.state["battle"]
        player, enemy = battle["player"], battle["enemy"]
        asset = world.asset("boss" if run.encounter == 3 else f"enemy-{run.encounter + 1}")
        turn = battle.get("turn", 0) + 1
        screen = DungeonScreen(
            f"FLOOR {ROMAN[run.floor]} — {world.name.upper()}",
            f"*{world.title}*\n"
            f"-# {'⚔ GUARDIAN' if run.encounter == 3 else '⚔ BATTLE'} · {run.encounter + 1}/4"
            f"　 ·　 TURN {turn} · **YOUR TURN**",
            color=world.color,
        )
        screen.fields = [
            (f"⚔ {enemy['name']}", vitality("HP", enemy["hp"], enemy["max_hp"], available_emojis=available_emojis)
             + ("\n" + effects(enemy) if effects(enemy) else "")
             + f"\n-# {intent_caption(run, battle)}"),
            (profile.fantasy_title,
             f"-# SOUL LV. {profile.level}\n"
             + vitality("HP", run.hp, profile.max_hp, filled_emoji=PLAYER_HP, available_emojis=available_emojis) + "\n"
             + vitality("MP", run.mp, profile.max_mp, filled_emoji=PLAYER_MP, available_emojis=available_emojis) + "\n"
             + f"-# ⚔ {profile.weapon_name} · WEAPON LV. {profile.weapon_level}"
             + (" · " + effects(player) if effects(player) else "")),
            ("📜 BATTLE LOG", recent_battle_log(battle.get("log", []), enemy_name=enemy["name"])),
        ]
        return screen, asset
    elif phase == "defeated":
        title = "☠ SOUL DEFEATED"
        text = f"{'THE SEAL' if run.floor == 10 else 'Floor ' + ROMAN[run.floor]} · Encounter {run.encounter + 1} / 4\n\nPermanent progression preserved.\nYour temporary battle state has ended. Return to Sanctuary to try this world again."
    elif phase in {"victory", "cleared", "complete"}:
        reward = run.state.get("reward", {})
        title = "✦ ENEMY DEFEATED" if phase == "victory" else "GUARDIAN FALLEN"
        text = f"**+{reward.get('xp', 0):,} XP**"
        if reward.get("owner_skip"):
            text = "Owner skipped this battle.\n" + text
        if reward.get("level", 1) > reward.get("old_level", 1):
            gains = reward["gains"]
            text += f"\n\n✦ SOUL AWAKENED\nLevel {reward['old_level']} → {reward['level']}\n"
            text += " · ".join(f"{label} +{gains[key]}" for label, key in
                              (("HP", "max_hp"), ("MP", "max_mp"), ("STR", "strength"),
                               ("DEX", "dexterity"), ("INT", "intelligence"), ("VIT", "vitality"), ("LUK", "luck")))
        if phase != "victory":
            text += f"\nFloor {ROMAN[run.floor]} complete · {world.boss.name}\n\n⚔ Weapon Level **{reward.get('weapon_before', 0)} → {reward.get('weapon_after', 0)}**\n\n" + world.narrative("completion", profile.alignment)
            asset = world.asset("boss")
    else:
        text = "Return to Sanctuary."
    screen = DungeonScreen(title, text, color=ORIGIN_COLOR if run.state.get("sequence") == "opening" else world.color)
    if cinematic:
        sequence = run.state.get("sequence", "core")
        screen.footer = "Your worldline is permanent" if sequence in {"ending", "choice"} else "Continue when ready · /dungeon resumes this scene"
        if sequence == "core" and "anchors" in run.state.get("reveals", ()):
            screen.fields.append(("Containment", "10 / 10 anchors dismantled · Veyra's own power returning"))
        return screen, asset
    if phase in {"intro", "story"}:
        screen.footer = f"{patron_name(profile.alignment)} accompanies you · Scene {run.state.get('lore_scene', 0) + 1}/{len(scenes)} · /dungeon resumes here"
    elif phase in ACTIVE_PHASES and run.floor < 10:
        screen.footer = f"{world.title} · Encounter {run.encounter + 1}/4 · /dungeon resumes this run"
    else:
        screen.footer = "/dungeon resumes saved scenes · progress belongs to your soul"
    return screen, asset


class DungeonView(discord.ui.LayoutView):
    command_name = "dungeon"

    def __init__(self, cog, owner, profile, run, *, guild_id=None, player_user=None, show_landing=False):
        super().__init__(timeout=180)
        self.cog, self.owner = cog, owner
        self.message = None
        self.lock = asyncio.Lock()
        self.closed = False
        self.profile, self.run = profile, run
        self.guild_id = guild_id
        self.asset = None
        self.asset_key = None
        self.player_user = player_user
        self.ability_menu_open = False
        self.confirm_abandon = False
        self.landing = bool(show_landing and run and run.phase in ACTIVE_PHASES)
        self.participant_ids = (owner,)
        self.refresh_buttons()

    def finish(self):
        if self.cog.duel_users.get(self.owner) is self:
            self.cog.duel_users.pop(self.owner, None)
        self.closed = True
        self.disable()
        self.stop()
        self.cog.release_view(self)

    def disable(self):
        for item in self.walk_children():
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True

    async def notice(self, interaction, text, *, response=False):
        sender = interaction.response.send_message if response else interaction.followup.send
        await sender(view=dungeon_notice(text), ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner:
            await self.notice(interaction, "This descent belongs to another soul. Open `/dungeon` for your own run.", response=True)
            return False
        if self.closed:
            await self.notice(interaction, "These controls have expired. Open `/dungeon` to resume your saved scene.", response=True)
            return False
        return True

    async def on_timeout(self):
        async with self.lock:
            if self.closed:
                return
            self.finish()
            # Keep the final black ending free of text, as the story requires.
            if not (self.run and self.run.phase == "complete"):
                self.container.add_item(discord.ui.TextDisplay(
                    "-# Controls expired · Open `/dungeon` to resume. Your soul progression is saved."
                ))
            if self.message:
                try:
                    await self.message.edit(view=self)
                except discord.HTTPException:
                    pass

    def build_layout(self):
        profile, run = self.profile, self.run
        available_emojis = usable_bar_emojis(self.cog.bot) if run and run.phase == "combat" else None
        screen, asset = dungeon_presentation(profile, run, available_emojis=available_emojis)
        phase = run.phase if run else "abandoned"
        if self.landing or phase == "abandoned":
            floor = run.floor if self.landing else min(10, profile.weapon_level + 1)
            world = world_for(floor)
            screen = DungeonScreen(
                "RESUME YOUR DESCENT" if self.landing else "RUN ABANDONED" if run else "THE TENFOLD DESCENT",
                f"**Floor {ROMAN[floor]} · {world.name}**\n{world.title}\n\n"
                + (f"Saved scene · {phase.replace('_', ' ').title()} · Encounter {run.encounter + 1}/4\n"
                   "Your next action continues exactly where you left off."
                   if self.landing else ("Your temporary run has ended. Permanent progression is preserved.\n\n" if run else "")
                   + "Ten worlds.\nTen guardians.\nOne path.\n\nSomething is waiting at the end.\n\nEncounter 1/4 awaits. Your soul's progress survives every failed run."),
                color=world.color,
                fields=[(f"✦ {profile.fantasy_title} · Soul Level {profile.level}",
                         f"{profile.class_name} · {profile.affinity_name}\n"
                         f"⚔ {profile.weapon_name} · Weapon Level {profile.weapon_level}\n"
                         f"Highest Floor {ROMAN[profile.highest_floor] or '—'}")],
                footer="Saved run available · Resume when ready" if self.landing else "Your awakened identity stays with you",
            )
            asset = world.asset()
        if self.confirm_abandon:
            screen = DungeonScreen("LEAVE THE DESCENT?",
                "Abandon this run and discard its temporary battle state?\n\n"
                "Your XP, Soul Level, weapon upgrades, and permanent progression are preserved.",
                color=0xA63842, footer="Cancel to return to your current scene")
        self.display_asset = asset if asset.is_file() else None
        battle_screen = phase == "combat" and not self.landing and not self.confirm_abandon
        self.container = discord.ui.Container(accent_color=screen.color)
        self.add_item(self.container)
        add = self.container.add_item
        heading = ""
        if screen.title:
            if screen.title != "THE TENFOLD DESCENT":
                heading = "-# THE TENFOLD DESCENT\n"
            heading += f"## {screen.title}"
        if screen.description:
            heading += "\n" + screen.description
        if heading:
            add(discord.ui.TextDisplay(heading))
        if self.display_asset:
            description = screen.title or "The final silence"
            if battle_screen:
                enemy = run.state["battle"]["enemy"]
                description = f"{enemy['name']} · HP {enemy['hp']} / {enemy['max_hp']} · {intent_caption(run, run.state['battle'])} · {effects(enemy)}"
            add(discord.ui.MediaGallery(discord.MediaGalleryItem(
                "attachment://dungeon.jpg", description=description[:1024]
            )))
        if battle_screen:
            for index, (name, value) in enumerate(screen.fields):
                if index == 0:
                    # Native live vitals keep attacks as small JSON edits. The
                    # approved illustration stays attached for this encounter.
                    # The static illustration already carries the enemy name.
                    # Keep a native heading only when artwork is unavailable.
                    add(discord.ui.TextDisplay(value if self.display_asset else f"**{name}**\n{value}"))
                    continue
                if index > 0:
                    add(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
                if index == 2:
                    add(discord.ui.TextDisplay(f"**{name}**\n{value}"))
                    continue
                # Keep vitals beside the avatar. Splitting them into a separate
                # display below the thumbnail leaves an avatar-height blank gap.
                title = discord.ui.TextDisplay(f"**{name}**\n{value}")
                avatar = getattr(self.player_user, "display_avatar", None)
                portrait = ("attachment://dungeon.jpg" if self.display_asset else None) if index == 0 else str(avatar.url) if avatar else None
                if portrait:
                    add(discord.ui.Section(title, accessory=discord.ui.Thumbnail(
                        portrait, description=run.state["battle"]["enemy"]["name"] if index == 0 else "Your Discord avatar")))
                else:
                    add(title)
            if self.ability_menu_open:
                player = run.state["battle"]["player"]
                cost = 16 if player["passive"] == "discount" and player["skills_used"] == 0 else 22
                self.add_item(discord.ui.TextDisplay(
                    f"**{player['signature_name']}** · {cost} MP\n{profile.signature_description}\n"
                    f"-# {max(0, 2 - player['skills_used'])} uses remaining this encounter"
                ))
            return
        for index, (name, value) in enumerate(screen.fields):
            if index == 0:
                add(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
            text = discord.ui.TextDisplay(f"### {name}\n{value}")
            is_player = (phase == "combat" and not self.landing and index == 1) or self.landing or phase == "abandoned"
            avatar = getattr(self.player_user, "display_avatar", None)
            if is_player and avatar:
                display_name = discord.utils.escape_markdown(self.player_user.display_name)
                text.content = f"{text.content}\n-# {display_name}"
                add(discord.ui.Section(text, accessory=discord.ui.Thumbnail(
                    str(avatar.url), description="Your Discord avatar")))
            else:
                add(text)
        if screen.footer:
            add(discord.ui.TextDisplay("-# " + screen.footer))
        if not self.container.children:
            add(discord.ui.Separator(visible=False))

    async def on_error(self, interaction, error, item):
        self.finish()
        error_id = self.cog.report(error, "dungeon_interface")
        try:
            await self.notice(interaction,
                "Your saved descent and soul progression remain safe. "
                f"Open `/dungeon` to resume.\nError ID: `{error_id}`",
            )
        except discord.HTTPException:
            pass

    def refresh_buttons(self):
        self.clear_items()
        self.build_layout()
        run = self.run
        phase = run.phase if run else "abandoned"
        token, revision = (run.token, run.revision) if run else (None, None)
        actions = []
        if phase == "complete":
            return
        if phase in {"abandoned", "defeated"}:
            actions = [("begin", "Return to Sanctuary" if phase == "defeated" else "Begin Descent", discord.ButtonStyle.primary)]
        elif phase == "combat":
            actions = [("attack", "Attack", discord.ButtonStyle.primary),
                       ("ability", "Ability", discord.ButtonStyle.primary),
                       ("guard", "Guard · +8 MP", discord.ButtonStyle.secondary)]
        else:
            label = "Face Guardian" if phase == "boss_intro" else "Continue"
            if phase == "cleared":
                label = f"Descend to Floor {ROMAN[min(10, run.floor + 1)]}"
            if phase in {"intro", "story"} and run.state.get("sequence") != "opening":
                beat = run.state.get("story_beat", 1)
                scenes = lore_scenes(world_for(run.floor), phase, self.profile.alignment, beat)
                if run.state.get("lore_scene", 0) + 1 < len(scenes):
                    label = "Read On"
                else:
                    label = "Approach Guardian" if phase == "story" and beat == 2 else "Enter Encounter"
            actions = [("continue", label, discord.ButtonStyle.primary)]
            if phase == "seal" and run.state.get("sequence") == "choice":
                actions = [("choose_meyaya", "🌸 Stand with Meyaya", discord.ButtonStyle.primary),
                           ("choose_veyra", "⚫ Stand with Veyra", discord.ButtonStyle.secondary)]
            elif phase == "seal" and run.state.get("sequence") == "ending":
                label = "Witness" if self.profile.ending_route == "meyaya" else "Continue"
                from bot.data.fantasy_memory_world import ending_scenes
                if run.state.get("scene", 0) == len(ending_scenes(self.profile.ending_route)) - 1:
                    label = "Let the text disappear" if self.profile.ending_route == "veyra" else "The world continues"
                actions = [("continue", label, discord.ButtonStyle.primary)]
        if phase in ACTIVE_PHASES and not getattr(self.profile, "ending_route", None):
            actions.append(("abandon", "Abandon Run", discord.ButtonStyle.danger))
        if self.landing:
            actions = [("resume", "Resume Descent", discord.ButtonStyle.primary)]
        if self.confirm_abandon:
            actions = [("confirm_abandon", "Abandon Run", discord.ButtonStyle.danger),
                       ("cancel_abandon", "Keep Descending", discord.ButtonStyle.secondary)]
        row = discord.ui.ActionRow()
        self.container.add_item(row)
        for action, label, style in actions:
            button = discord.ui.Button(label=label, style=style,
                                       custom_id=f"dungeon:{token or 'entry'}:{revision or 0}:{action}")
            if phase == "combat" and action in {"attack", "ability", "guard", "abandon"}:
                button.emoji = {"attack": "⚔️", "ability": "✨", "guard": "🛡️", "abandon": "🏃"}[action]
                button.row = 0
            if action == "ability":
                player = run.state["battle"]["player"]
                cost = 16 if player["passive"] == "discount" and player["skills_used"] == 0 else 22
                button.label = f"Ability · {cost} MP"
                button.disabled = not player.get("signature") or player["mp"] < cost or player["skills_used"] >= 2

            async def callback(interaction, action=action, token=token, revision=revision):
                if action == "ability":
                    await self.show_abilities(interaction, token, revision)
                elif action in {"resume", "abandon", "cancel_abandon"}:
                    await self.local_action(interaction, action, token, revision)
                else:
                    await self.play(interaction, "abandon" if action == "confirm_abandon" else action, token, revision)

            button.callback = callback
            row.add_item(button)
        if phase == "combat" and self.ability_menu_open and not self.confirm_abandon and not self.landing:
            player = run.state["battle"]["player"]
            if player.get("signature"):
                cost = 16 if player["passive"] == "discount" and player["skills_used"] == 0 else 22
                menu = discord.ui.Select(placeholder="Choose your awakened signature", row=1,
                    custom_id=f"dungeon:{token}:{revision}:signature",
                    options=[discord.SelectOption(label=player["signature_name"][:100], value="ability",
                        description=(f"{cost} MP · {2 - player['skills_used']} uses left · " + getattr(self.profile, "signature_description", ""))[:100])],
                    disabled=player["mp"] < cost or player["skills_used"] >= 2)

                async def select_signature(interaction, token=token, revision=revision):
                    await self.play(interaction, "ability", token, revision)

                menu.callback = select_signature
                # Expanded ability details follow the main HUD in this same
                # message; keep their selector directly beneath them.
                self.add_item(discord.ui.ActionRow(menu))

    async def local_action(self, interaction, action, token, revision):
        if not await self.interaction_check(interaction):
            return
        await interaction.response.defer()
        async with self.lock:
            if self.closed or not self.run or self.run.token != token or self.run.revision != revision:
                await self.notice(interaction, "This scene has changed. Open `/dungeon` to resume.")
                return
            self.landing = False
            self.confirm_abandon = action == "abandon"
            await self.deliver(interaction.edit_original_response)

    async def show_abilities(self, interaction, token, revision):
        if not await self.interaction_check(interaction):
            return
        async with self.lock:
            if self.closed or self.run.token != token or self.run.revision != revision or self.run.phase != "combat":
                await self.notice(interaction, "Open `/dungeon` to resume your current turn.", response=True)
                return
            self.ability_menu_open = not self.ability_menu_open
            self.refresh_buttons()
            await interaction.response.edit_message(view=self)

    async def play(self, interaction, action, token, revision):
        # Explicit check also protects direct callback invocation in tests.
        if not await self.interaction_check(interaction):
            return
        self.player_user = interaction.user
        started = perf_counter()
        stages = {}

        async def acknowledge():
            began = perf_counter()
            try:
                await interaction.response.defer()
            finally:
                stages["ack_ms"] = round((perf_counter() - began) * 1000, 2)

        # Start the acknowledgement immediately, but don't serialize its HTTP
        # round trip ahead of the database transaction. Notifications/edits wait
        # for it, and the existing per-run lock still serializes saved actions.
        acknowledgement = asyncio.create_task(acknowledge())
        status = "error"
        try:
            await self._play_acknowledged(interaction, action, token, revision, acknowledgement, stages)
            status = "handled"
        finally:
            await asyncio.gather(acknowledgement, return_exceptions=True)
            event("dungeon_action_timing", command="dungeon", action=action,
                  total_ms=round((perf_counter() - started) * 1000, 2), stages=stages, status=status)

    async def _play_acknowledged(self, interaction, action, token, revision, acknowledgement, stages):
        async def notify(text):
            await acknowledgement
            await self.notice(interaction, text)

        waiting = perf_counter()
        async with self.lock:
            stages["lock_wait_ms"] = round((perf_counter() - waiting) * 1000, 2)
            if self.closed:
                await notify("Open `/dungeon` to resume your saved run.")
                return
            if action == "abandon" and not self.confirm_abandon:
                await notify("That confirmation has closed. Use Abandon Run to review the choice again.")
                return
            if action == "begin":
                busy = self.cog.duel_users.get(self.owner)
                if self.owner in self.cog.pending or (busy is not None and busy is not self):
                    await notify("Finish your current fantasy activity first.")
                    return
                if len(self.cog.duel_users) >= 32 and busy is None:
                    await notify("The arenas are busy. Try again shortly.")
                    return
                self.cog.duel_users[self.owner] = self
            database_started = perf_counter()
            try:
                previous_phase = self.run.phase if self.run else None
                async with asyncio.timeout(10):
                    async with self.cog.bot.db_session() as session:
                        self.profile, self.run = await DungeonService(session).transition(
                            self.owner, action, token=token, revision=revision,
                            guild_id=interaction.guild_id or 0,
                        )
            except DungeonStale as error:
                if action == "begin" and self.cog.duel_users.get(self.owner) is self:
                    self.cog.duel_users.pop(self.owner, None)
                await notify(str(error))
                return
            except DungeonUnavailable as error:
                if action == "begin" and self.cog.duel_users.get(self.owner) is self:
                    self.cog.duel_users.pop(self.owner, None)
                await notify(str(error))
                return
            finally:
                stages["database_ms"] = round((perf_counter() - database_started) * 1000, 2)
            await acknowledgement
            self.ability_menu_open = False
            self.confirm_abandon = False
            self.landing = False
            await self.present_transition(interaction, previous_phase)
            if self.run.phase not in ACTIVE_PHASES:
                if self.cog.duel_users.get(self.owner) is self:
                    self.cog.duel_users.pop(self.owner, None)

    async def present_transition(self, interaction, previous_phase):
        # A component defer targets this same message. One edit updates story,
        # battle and victory alike, retaining unchanged attachments and avoiding
        # a followup upload plus deletion for every page of dialogue.
        await self.deliver(interaction.edit_original_response)

    async def deliver(self, sender, *, initial=False):
        started, api_ms = perf_counter(), 0
        upload_bytes = 0

        async def measured_sender(**kwargs):
            nonlocal api_ms, upload_bytes
            files = [kwargs["file"]] if "file" in kwargs else kwargs.get("attachments", [])
            for image in files:
                if isinstance(image, discord.File):
                    position = image.fp.tell()
                    image.fp.seek(0, 2)
                    upload_bytes += image.fp.tell()
                    image.fp.seek(position)
            began = perf_counter()
            try:
                return await sender(**kwargs)
            finally:
                api_ms += (perf_counter() - began) * 1000

        try:
            async with asyncio.timeout(15):
                return await self._deliver(measured_sender, initial=initial)
        finally:
            elapsed = (perf_counter() - started) * 1000
            event("dungeon_delivery_timing", command="dungeon", initial=initial,
                  render_ms=round(max(0, elapsed - api_ms), 2), delivery_ms=round(api_ms, 2),
                  upload_bytes=upload_bytes)

    async def _deliver(self, sender, *, initial=False):
        self.refresh_buttons()
        asset = self.display_asset
        hero = None
        enemy_name = (self.run.state["battle"]["enemy"]["name"]
                      if self.run and self.run.phase == "combat" and not self.landing else "")
        asset_key = (str(asset), asset.stat().st_mtime_ns, enemy_name) if asset else None
        # discord.py sets IS_COMPONENTS_V2 from LayoutView. No classic content or
        # embeds may accompany the payload. Edits explicitly clear legacy text.
        kwargs = dict(view=self, allowed_mentions=discord.AllowedMentions.none())
        if not initial:
            kwargs.update(content=None, embeds=[])
        if asset:
            if initial or asset_key != self.asset_key:
                if hero is None:
                    try:
                        hero = await asyncio.to_thread(render_scene_art, *asset_key)
                    except (OSError, ValueError):
                        logger.warning("Dungeon image resize failed; uploading original artwork", exc_info=True)
                with closing(discord.File(BytesIO(hero) if hero is not None else str(asset), filename="dungeon.jpg")) as image:
                    kwargs["file" if initial else "attachments"] = image if initial else [image]
                    result = await sender(**kwargs)
            else:
                result = await sender(**kwargs)
            self.asset = asset
            self.asset_key = asset_key
        else:
            # Text remains usable if an asset was damaged during deployment.
            if not initial:
                kwargs["attachments"] = []
            result = await sender(**kwargs)
            self.asset = None
            self.asset_key = None
        if initial:
            self.message = result
