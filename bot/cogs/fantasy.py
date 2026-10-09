"""Permanent awakenings: database first, bounded visual reveal second."""

import asyncio
import json
import logging
import secrets
from collections import OrderedDict
from contextlib import nullcontext
from io import BytesIO
from time import monotonic
from types import SimpleNamespace
from typing import Literal
from bot.services.fantasy_boss import meyaya_boss_profile
from bot.services.meyaya_boss_combat import BossDuelEngine, public_fighter
from bot.services.meyaya_boss_presentation import BossPresentation
from bot.services.fantasy_boss import veyra_boss_profile, VEYRA_BOSS_ID
from bot.services.patron_boss_combat import VeyraDuelEngine, PatronClashEngine
from bot.services.patron_boss_presentation import VeyraPresentation, PatronClashPresentation
from bot.utils.fantasy_profile_target import FantasyProfileTarget

import discord
from discord.ext import commands

from bot.logging.health import health
from bot.services.fantasy_profile import FantasyProfileService, REBIRTH_COOLDOWN, utc
from datetime import UTC, datetime
from bot.views.fantasy_rebirth import RebirthView
from bot.repositories.fantasy_dungeon import FantasyDungeonRepository
from bot.services.fantasy_dungeon import DungeonService, DungeonUnavailable
from bot.data.private_identity import AYAYA_USER_ID
from bot.views.fantasy_dungeon import DungeonView, dungeon_notice
from bot.services.fantasy_render import render_ritual, render_soul_card
from bot.services.fantasy_weapon_render import render_weapon_acquisition
from bot.services.fantasy_duel import DuelEngine, Fighter, RULES_VERSION
from bot.services.fantasy_duel_renderer import render_duel
from bot.repositories.fantasy_duels import FantasyDuelRepository
from bot.views.fantasy_duel import DuelChallengeView, DuelResultView
from bot.services.fantasy_guardian import bound_guardian
from bot.services.guardian_render import guardian_card
from bot.utils.command_context import CommandOutput, remember_command_result
from bot.utils.embeds import meyaya_embed
from bot.utils.image_work import BoundedImageGate, image_work, animation_work
from bot.views.fantasy import (
    AlreadyAwakenedView,
    AwakeningView,
    AwakeningRevealView,
    FantasyProfileView,
    soul_embed,
)

logger = logging.getLogger(__name__)
MAX_VIEWS = 64
BOSS_ENCOUNTER_TIMEOUT = 180
DUEL_DELIVERY_TIMEOUT = 15


def result_summary(profile, member):
    if getattr(profile, "is_meyaya_boss", False):
        return dict(
            target_id=profile.user_id,
            target_name="Meyaya",
            class_name="Soulweaver",
            title="The Girl at the End of Every Story",
            hp="UNKNOWN",
            mp="UNKNOWN",
            potential="ANALYSIS FAILED",
            weapon=profile.weapon_name,
            passive="Spell Memory",
            signature="Prism Cascade",
            authority="Soul Interface",
        )
    return dict(
        target_id=profile.user_id,
        target_name=member.display_name[:100],
        class_name=profile.class_name,
        subclass=profile.subclass_name,
        affinity=profile.affinity_name,
        stats=profile.base_stats,
        weapon=profile.weapon_name,
        rarity=profile.weapon_rarity,
        passive=profile.passive_name,
        signature=profile.signature_name,
        title=profile.fantasy_title,
        alignment=getattr(profile, "alignment", "unclaimed"),
        method="Saved fantasy identity until confirmed rebirth; local generation, not a factual personality assessment.",
    )


class FantasyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.views = set()
        self.pending = {}
        self.duel_users = {}
        self.duel_cooldowns = OrderedDict()
        self.clash_cooldowns = OrderedDict()
        self.render_slots = BoundedImageGate(capacity=4, concurrency=2)

    def track_view(self, view):
        if len(self.views) >= MAX_VIEWS:
            view.stop()
            raise commands.CommandError("The Soul Interface is busy. Please try again shortly.")
        self.views.add(view)

    def release_view(self, view):
        self.views.discard(view)
        if self.pending.get(view.owner) is view:
            self.pending.pop(view.owner, None)

    def cog_unload(self):
        for view in tuple(self.views):
            view.finish()

    async def get_profile(self, user_id):
        if user_id == getattr(getattr(self.bot, "user", None), "id", None):
            return meyaya_boss_profile(user_id)
        async with asyncio.timeout(10):
            async with self.bot.db_session() as session:
                return await FantasyProfileService(session).get(user_id)

    async def awaken_user(self, user_id):
        async with asyncio.timeout(10):
            async with self.bot.db_session() as session:
                return await FantasyProfileService(session).awaken(user_id)

    async def rebirth_user(self, user_id, expected_awakening):
        async with asyncio.timeout(10):
            async with self.bot.db_session() as session:
                return await FantasyProfileService(session).rebirth(user_id, expected_awakening)

    async def align_user(self, user_id, expected_awakening, choice):
        if user_id in self.duel_users:
            from bot.services.fantasy_profile import AlignmentUnavailable

            raise AlignmentUnavailable("Finish your current battle before sealing your oath.")
        async with asyncio.timeout(10):
            async with self.bot.db_session() as session:
                return await FantasyProfileService(session).choose_alignment(
                    user_id, expected_awakening, choice
                )

    def report(self, error, stage):
        error_id = health.capture(
            error,
            command=(
                "guardianbattle"
                if stage.startswith("guardian_duel")
                else (
                    "guardian"
                    if stage.startswith("guardian")
                    else "versus" if "duel" in stage else "awaken"
                )
            ),
            stage=stage,
        )
        logger.warning(
            "fantasy_failed stage=%s error_id=%s exception=%s",
            stage,
            error_id,
            type(error).__name__,
        )
        return error_id

    async def create_duel(self, left, right):
        boss = right.id == getattr(getattr(self.bot, "user", None), "id", None)
        if left.id == right.id or left.bot or (right.bot and not boss):
            raise commands.CommandError("Choose another human member or Meyaya to challenge.")
        if left.guild.id != right.guild.id:
            raise commands.CommandError("Both fighters must be in this server.")
        ids = (left.id,) if boss else (left.id, right.id)

        def available():
            if any(user_id in self.pending for user_id in ids):
                raise commands.CommandError("Finish the open awakening or rebirth before battling.")
            if any(user_id in self.duel_users for user_id in ids):
                raise commands.CommandError("One of these fighters already has an open duel.")
            if len(self.duel_users) >= 32:
                raise commands.CommandError("The arenas are busy. Try again shortly.")
            if monotonic() - self.duel_cooldowns.get(left.id, -100) < 15:
                raise commands.CommandError(
                    "Let the arena settle for 15 seconds before another challenge."
                )

        available()
        await self.check_dungeon_activity(*ids)
        members = (left, right)
        loaded = await asyncio.gather(
            *(self.get_profile(member.id) for member in members), return_exceptions=True
        )
        for profile in loaded:
            if isinstance(profile, BaseException):
                raise profile
        profiles = {member.id: profile for member, profile in zip(members, loaded)}
        if any(profile is None for profile in profiles.values()):
            raise commands.CommandError("Both fighters need a saved identity. Use `/awaken` first.")
        # Recheck after database awaits; admission and reservation are atomic on this loop.
        available()
        view = DuelChallengeView(self, left, right, profiles)
        self.track_view(view)
        for user_id in ids:
            self.duel_users[user_id] = view
        self.duel_cooldowns[left.id] = monotonic()
        self.duel_cooldowns.move_to_end(left.id)
        while len(self.duel_cooldowns) > 512:
            self.duel_cooldowns.popitem(last=False)
        safe = lambda text: discord.utils.escape_markdown(discord.utils.escape_mentions(str(text)))
        embed = meyaya_embed(
            "The arena calls",
            f"**{safe(left.display_name)}** challenges **{safe(right.display_name)}**.\nOnly the challenged member can accept.\n\nTemporary combat · no XP, rewards or permanent changes",
            icon="⚔",
        )
        for member in (left, right):
            p = profiles[member.id]
            embed.add_field(
                name=safe(member.display_name),
                value=f"{p.class_name} · {p.affinity_name}\n{p.weapon_name} ({p.weapon_rarity})",
                inline=True,
            )
        embed.set_footer(
            text="Challenge expires in 90 seconds · saved awakening stats decide the fight"
        )
        return embed, view

    async def run_duel(self, view, interaction):
        boss_key = getattr(view.profiles[view.right.id], "boss_key", "")
        is_boss = bool(boss_key) or view.right.id == getattr(
            getattr(self.bot, "user", None), "id", None
        )
        clash = getattr(view, "patron_clash", False)
        engine_type = (
            PatronClashEngine
            if clash
            else (
                VeyraDuelEngine
                if boss_key == "veyra"
                else BossDuelEngine if is_boss else DuelEngine
            )
        )
        engine = engine_type(
            *(
                Fighter.snapshot(view.profiles[m.id], m.display_name)
                for m in (view.left, view.right)
            ),
            seed=secrets.randbits(63),
        )
        state = engine.state
        # Keep immutable starting combat inputs for reproducibility, not full profiles.
        initial = [public_fighter(state.left), public_fighter(state.right)]
        portraits, palettes = [], []
        result_view = None
        battle_message = None
        image_delivery_failed = False
        boss_comment = state.dialogue
        presentation = (
            PatronClashPresentation
            if clash
            else VeyraPresentation if boss_key == "veyra" else BossPresentation
        )
        cinematic = presentation(self, view, interaction.channel) if is_boss else None
        try:
            view.message = await interaction.edit_original_response(
                content=None,
                embed=meyaya_embed(
                    (
                        "The authorities collide"
                        if clash
                        else (
                            "Hostile presence detected"
                            if boss_key == "veyra"
                            else "The author accepts" if is_boss else "Challenge accepted"
                        )
                    ),
                    (
                        "The encounter is temporary. Your awakening stays untouched."
                        if is_boss
                        else "The versus image, live battle and result will appear below. Both saved identities remain unchanged."
                    ),
                    icon="⚔",
                ),
                view=view,
                allowed_mentions=discord.AllowedMentions.none(),
            )

            async def inspect_fighter(member):
                if getattr(member, "patron_key", None) or clash:
                    return b"", ()
                try:
                    async with asyncio.timeout(8):
                        visual = await self.bot.build_profile_aesthetic_service().inspect(member)
                    return visual.avatar or b"", visual.palette
                except Exception as error:
                    self.report(error, "fantasy_duel_palette")
                    return b"", ()

            async with asyncio.TaskGroup() as group:
                visuals = [
                    group.create_task(inspect_fighter(member)) for member in (view.left, view.right)
                ]
            for visual in visuals:
                avatar, palette = visual.result()
                portraits.append(avatar)
                palettes.append(palette)
            if cinematic:
                await cinematic.intro(state)

            async def frame(*, intro=False, outcome=False, controls=None, history_note=""):
                nonlocal battle_message, boss_comment, image_delivery_failed
                if view.closed:
                    raise commands.CommandError("This duel has ended.")
                safe = lambda text: discord.utils.escape_markdown(
                    discord.utils.escape_mentions(str(text))
                )
                title = (
                    "An encounter begins"
                    if intro
                    else (
                        "Duel complete"
                        if state.finished
                        else f"Move {state.moves} · Round {state.round}"
                    )
                )
                lines = [
                    (
                        f"**{safe(f.name)}** · HP ??? / ??? · MP ??? / ???\n"
                        f"✦ **{safe(f.class_name)}** · Soul Pressure: UNREADABLE"
                        if f.is_boss
                        else f"**{safe(f.name)}** · HP {f.hp}/{f.max_hp} · MP {f.mp}/{f.max_mp}"
                    )
                    for f in (state.left, state.right)
                ]
                if state.finished:
                    winner = next(
                        (f.name for f in (state.left, state.right) if f.user_id == state.winner_id),
                        None,
                    )
                    lines.append(
                        f"\n**{safe(winner)} wins!**"
                        if winner
                        else "\n**Draw · neither fighter yields.**"
                    )
                    lines.append(
                        state.verdict + (f" · Finisher: {state.finisher}" if state.finisher else "")
                    )
                if state.history:
                    lines.append("\n**Recent events · newest first**")
                    lines.extend(safe(line) for line in reversed(state.history[-3:]))
                if history_note:
                    lines.append(history_note)
                embed = meyaya_embed(title, "\n".join(lines), icon="⚔")
                boss_colour = 0xDC143C if state.right.boss_key == "veyra" else 0xEEB4E4
                if cinematic:
                    embed.colour = boss_colour
                embed.set_footer(text=f"{state.arena[0]} · Temporary combat · identities unchanged")
                png = None
                try:
                    if not image_delivery_failed or state.finished:
                        async with self.render_slots:
                            png = await image_work(
                                render_duel, state, tuple(portraits), tuple(palettes), intro=intro
                            )
                except Exception as error:
                    self.report(error, "fantasy_duel_render")
                if png:
                    embed.set_image(url="attachment://meyaya-duel.png")
                boss_content = None
                if cinematic and not intro:
                    if state.dialogue:
                        boss_comment = state.dialogue
                    boss_content = f"## {safe(title if state.finished else state.boss_form)}"
                    if not state.finished and boss_comment:
                        boss_content += f"\n**{safe(boss_comment)}**"
                    if state.finished:
                        boss_content += "\n" + (
                            f"**{safe(winner)} wins.**" if winner else "**Neither fighter yields.**"
                        )
                    elif state.history:
                        boss_content += "\n" + "\n".join(safe(line) for line in state.history[-2:])
                    boss_content = boss_content[:1950]
                # Every boss frame uses a full-size image inside its themed embed.
                kwargs = dict(
                    content=boss_content
                    or (history_note if outcome and png and history_note else None),
                    embed=(
                        discord.Embed(colour=boss_colour).set_image(
                            url="attachment://meyaya-duel.png"
                        )
                        if cinematic and png
                        else None if (intro or outcome) and png else embed
                    ),
                    view=controls,
                    attachments=(
                        [discord.File(BytesIO(png), filename="meyaya-duel.png")] if png else []
                    ),
                    allowed_mentions=discord.AllowedMentions.none(),
                )

                async def deliver_frame():
                    if intro or outcome or battle_message is None:
                        send_kwargs = dict(kwargs)
                        send_kwargs["files"] = send_kwargs.pop("attachments")
                        return await interaction.channel.send(**send_kwargs)
                    return await battle_message.edit(**kwargs)

                try:
                    async with asyncio.timeout(DUEL_DELIVERY_TIMEOUT):
                        message = await deliver_frame()
                except (discord.HTTPException, TimeoutError) as error:
                    if not png:
                        raise
                    self.report(error, "fantasy_duel_delivery")
                    # A stalled upload must not consume the whole encounter deadline.
                    # Keep subsequent turns text-only, then retry the final result art.
                    image_delivery_failed = True
                    embed.set_image(url=None)
                    kwargs["embed"] = embed
                    kwargs["attachments"] = []
                    async with asyncio.timeout(DUEL_DELIVERY_TIMEOUT):
                        message = await deliver_frame()
                if not intro and not outcome:
                    battle_message = message
                view.message = message
                return message

            await frame(intro=True)
            await asyncio.sleep(3)
            while not state.finished:
                engine.advance_move()
                await frame()
                if not state.finished:
                    await asyncio.sleep(1.5)
            note = ""
            summary = dict(
                inputs=initial,
                moves=state.moves,
                verdict=state.verdict,
                finisher=state.finisher,
                fighters=[
                    (
                        public_fighter(f)
                        if f.is_boss
                        else dict(
                            user_id=f.user_id,
                            hp=f.hp,
                            mp=f.mp,
                            damage_dealt=f.damage_dealt,
                            damage_taken=f.damage_taken,
                            criticals=f.critical_hits,
                            dodges=f.dodges,
                            skills=f.skills_used,
                        )
                    )
                    for f in (state.left, state.right)
                ],
            )
            if is_boss:
                summary.update(
                    encounter="patron_clash" if clash else f"{boss_key or 'meyaya'}_boss",
                    boss_rules_version=2,
                    adaptive_class=state.boss_form,
                    memory_count=state.memory_count,
                )
                # Boss damage-taken can reconstruct hidden health over a fight.
                summary["fighters"][0].pop("damage_dealt", None)
            try:
                async with asyncio.timeout(5):
                    async with self.bot.db_session() as session:
                        async with session.begin():
                            await FantasyDuelRepository(session).record(
                                dict(
                                    id=view.token,
                                    guild_id=view.left.guild.id,
                                    challenger_id=view.left.id,
                                    opponent_id=view.right.id,
                                    winner_id=state.winner_id,
                                    seed=state.seed,
                                    rules_version=RULES_VERSION,
                                    rounds=state.round,
                                    arena=state.arena[0],
                                    summary=summary,
                                )
                            )
            except Exception as error:
                error_id = self.report(error, "fantasy_duel_history")
                note = f"Result history could not be saved. Error ID: `{error_id}`"
            if cinematic:
                await cinematic.finish(state, history_note=note)
                message = cinematic.message
            else:
                result_view = DuelResultView(self, view.left, view.right, view.profiles, state)
                result_view.task = view.task
                self.release_view(view)
                self.track_view(result_view)
                result_view.message = await frame(
                    outcome=True, controls=result_view, history_note=note
                )
                message = result_view.message
            outputs = getattr(self.bot, "_meyaya_command_outputs", None)
            if outputs is None:
                outputs = self.bot._meyaya_command_outputs = OrderedDict()
            outputs[(message.channel.id, message.id)] = (
                monotonic(),
                CommandOutput(
                    "versus",
                    view.owner,
                    view.left.display_name[:80],
                    json.dumps(
                        dict(
                            challenger=state.left.name,
                            opponent=state.right.name,
                            winner_id=state.winner_id,
                            rounds=state.round,
                            moves=state.moves,
                            verdict=state.verdict,
                            fighters=[
                                (
                                    public_fighter(f)
                                    if f.is_boss
                                    else dict(
                                        user_id=f.user_id,
                                        name=f.name,
                                        class_name=f.class_name,
                                        affinity=f.affinity_name,
                                        weapon=f.weapon,
                                        hp=f.hp,
                                        max_hp=f.max_hp,
                                        mp=f.mp,
                                        max_mp=f.max_mp,
                                        damage="UNMEASURABLE" if is_boss else f.damage_dealt,
                                        crits=f.critical_hits,
                                        dodges=f.dodges,
                                        skills=f.skills_used,
                                        stats=[
                                            f.strength,
                                            f.dexterity,
                                            f.intelligence,
                                            f.vitality,
                                            f.luck,
                                        ],
                                    )
                                )
                                for f in (state.left, state.right)
                            ],
                            method="Seeded local combat using saved awakening stats; no permanent changes.",
                        ),
                        ensure_ascii=False,
                    )[:2000],
                ),
            )
            while len(outputs) > 512:
                outputs.popitem(last=False)
        except BaseException:
            if result_view:
                result_view.finish()
            try:
                async with asyncio.timeout(2):
                    edit = (
                        battle_message.edit
                        if battle_message
                        else interaction.edit_original_response
                    )
                    await edit(
                        content="The duel was interrupted. Both fantasy identities are unchanged.",
                        embed=None,
                        attachments=[],
                        view=None,
                    )
            except (Exception, asyncio.CancelledError):
                pass
            raise

    @staticmethod
    def view_guild_id(view):
        return getattr(view, "guild_id", None) or getattr(
            getattr(getattr(view, "left", None), "guild", None), "id", None
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        for view in tuple(self.views):
            if (
                member.id in getattr(view, "participant_ids", ())
                and self.view_guild_id(view) == member.guild.id
            ):
                view.finish()

    @commands.Cog.listener()
    async def on_raw_member_remove(self, payload):
        for view in tuple(self.views):
            if (
                payload.user.id in getattr(view, "participant_ids", ())
                and self.view_guild_id(view) == payload.guild_id
            ):
                view.finish()

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        for view in tuple(self.views):
            if self.view_guild_id(view) == guild.id:
                view.finish()

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload):
        for view in tuple(self.views):
            if payload.message_id in {
                getattr(getattr(view, "message", None), "id", None),
                getattr(getattr(view, "cinematic_message", None), "id", None),
            } and hasattr(view, "participant_ids"):
                view.finish()

    @commands.hybrid_command(
        description="Challenge a member, or face Meyaya's adaptive final-boss encounter."
    )
    @commands.guild_only()
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def versus(self, ctx, member: FantasyProfileTarget):
        await ctx.defer()
        if isinstance(member, str):
            await self.start_patron_encounter(ctx, member)
            return
        embed, view = await self.create_duel(ctx.author, member)
        try:
            if member.id == getattr(getattr(self.bot, "user", None), "id", None):
                view.running = True
                for child in view.children:
                    child.disabled = True
                view.message = await ctx.send(
                    embed=meyaya_embed(
                        "The Soul Interface hears you",
                        f"**{discord.utils.escape_mentions(ctx.author.display_name)}** challenged Meyaya.\n\n*The girl at the end of every story smiles.*",
                        icon="✦",
                    ),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                view.task = asyncio.current_task()
                try:
                    async with asyncio.timeout(BOSS_ENCOUNTER_TIMEOUT):
                        await self.run_duel(
                            view,
                            SimpleNamespace(
                                channel=ctx.channel, edit_original_response=view.message.edit
                            ),
                        )
                finally:
                    view.finish()
                return
            remember_command_result(
                ctx,
                challenger_id=ctx.author.id,
                opponent_id=member.id,
                status="Awaiting opponent consent; no battle result yet.",
            )
            view.message = await ctx.send(
                embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none()
            )
        except BaseException:
            view.finish()
            raise

    async def start_patron_encounter(self, ctx, patron, *, clash=False):
        def available():
            activity = self.duel_users.get(ctx.author.id)
            if ctx.author.id in self.pending or (
                activity is not None and not isinstance(activity, DungeonView)
            ):
                raise commands.CommandError("Finish your current fantasy activity first.")
            if len(self.duel_users) >= 32 or len(self.views) >= MAX_VIEWS:
                raise commands.CommandError("The arenas are busy. Try again shortly.")
            if monotonic() - self.duel_cooldowns.get(ctx.author.id, -100) < 15:
                raise commands.CommandError(
                    "Let the arena settle for 15 seconds before another challenge."
                )
            if clash and monotonic() - self.clash_cooldowns.get(ctx.guild.id, -100) < 60:
                raise commands.CommandError("Let this world's collision settle for 60 seconds.")

        available()
        # Patron fights use temporary snapshots. A saved descent can be paused
        # without abandoning it or changing its HP, progression, or rewards.
        meyaya = SimpleNamespace(
            id=self.bot.user.id,
            guild=ctx.guild,
            bot=True,
            display_name="Meyaya",
            patron_key="meyaya",
        )
        veyra = SimpleNamespace(
            id=VEYRA_BOSS_ID, guild=ctx.guild, bot=True, display_name="Veyra", patron_key="veyra"
        )
        left = meyaya if clash else ctx.author
        right = veyra if clash or patron == "veyra" else meyaya
        left_profile = meyaya_boss_profile(left.id) if clash else await self.get_profile(left.id)
        if left_profile is None:
            raise commands.CommandError(
                "Awaken your soul with `/awaken` before challenging a patron."
            )
        profiles = {
            left.id: left_profile,
            right.id: veyra_boss_profile() if right is veyra else meyaya_boss_profile(right.id),
        }
        available()
        view = DuelChallengeView(self, left, right, profiles)
        view.owner = ctx.author.id
        view.participant_ids = (ctx.author.id,)
        view.patron_clash = clash
        view.running = True
        for child in view.children:
            child.disabled = True
        dungeon = self.duel_users.get(ctx.author.id)
        async with dungeon.lock if isinstance(dungeon, DungeonView) else nullcontext():
            available()
            if self.duel_users.get(ctx.author.id) is not dungeon:
                raise commands.CommandError("Your activity changed. Try `/bossfight` again.")
            self.track_view(view)
            if isinstance(dungeon, DungeonView):
                dungeon.finish()
            self.duel_users[ctx.author.id] = view
        self.duel_cooldowns[ctx.author.id] = monotonic()
        self.duel_cooldowns.move_to_end(ctx.author.id)
        while len(self.duel_cooldowns) > 512:
            self.duel_cooldowns.popitem(last=False)
        if clash:
            self.clash_cooldowns[ctx.guild.id] = monotonic()
            self.clash_cooldowns.move_to_end(ctx.guild.id)
            while len(self.clash_cooldowns) > 512:
                self.clash_cooldowns.popitem(last=False)
        view.task = asyncio.current_task()
        try:
            view.message = await ctx.send(
                "The Soul Interface is opening the arena…",
                allowed_mentions=discord.AllowedMentions.none(),
            )
            async with asyncio.timeout(BOSS_ENCOUNTER_TIMEOUT):
                await self.run_duel(
                    view,
                    SimpleNamespace(channel=ctx.channel, edit_original_response=view.message.edit),
                )
        finally:
            view.finish()

    @commands.hybrid_command(
        description="Challenge Meyaya or Veyra, or witness their world-shattering clash."
    )
    @commands.guild_only()
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def bossfight(self, ctx, boss: Literal["meyaya", "veyra", "clash"] = "veyra"):
        await ctx.defer()
        await self.start_patron_encounter(
            ctx, "veyra" if boss == "clash" else boss, clash=boss == "clash"
        )

    @commands.command(
        hidden=True, description="Witness Meyaya versus Veyra: Origin clashes with Erasure."
    )
    @commands.guild_only()
    @commands.cooldown(1, 60, commands.BucketType.guild)
    async def bossbattle(self, ctx):
        await ctx.defer()
        await self.start_patron_encounter(ctx, "veyra", clash=True)

    @commands.hybrid_command(description="View the soul-bound guardian linked to an awakening.")
    @commands.cooldown(1, 8, commands.BucketType.user)
    async def guardian(self, ctx, member: discord.Member | None = None):
        await ctx.defer()
        member = member or ctx.author
        profile = await self.get_profile(member.id)
        if profile is None:
            await ctx.send("Their soul has not awakened. Use `/awaken` before meeting a guardian.")
            return
        g = bound_guardian(profile)
        remember_command_result(
            ctx,
            target_id=member.id,
            target_name=member.display_name,
            guardian=g.name,
            affinity=g.affinity_name,
            guardian_hp=g.max_hp,
            guardian_mp=g.max_mp,
            blessing=g.blessing,
            method="Stable companion derived from the saved awakening, not a daily draw.",
        )
        embed = meyaya_embed(
            g.name,
            f"{g.affinity_name} · {g.owner_class}\nHP {g.max_hp} · MP {g.max_mp}\nATK {g.attack} · DEF {g.defense} · SPD {g.speed}\n{g.blessing}: {g.blessing_text}\n{g.weakness}",
            icon="✦",
        )
        data = None
        try:
            async with self.render_slots:
                data = await image_work(guardian_card, g, member.display_name)
        except Exception as error:
            self.report(error, "guardian_render")
        try:
            if data:
                await ctx.send(
                    file=discord.File(BytesIO(data), filename="guardian.png"),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            else:
                await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            if not data:
                raise
            await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    async def card_bytes(self, profile, member):
        async with self.render_slots:
            if getattr(profile, "is_meyaya_boss", False):
                return await image_work(render_soul_card, profile, member.display_name)
            avatar = b""
            asset = None
            try:
                asset = member.display_avatar.with_size(512).with_format("png")
                async with asyncio.timeout(3):
                    avatar = await self.bot.build_profile_aesthetic_service()._download(str(asset))
            except Exception as error:
                # A portrait outage must not stop an already saved identity.
                self.report(error, "fantasy_avatar")
            if not avatar and asset is not None:
                # The shared downloader returns None on CDN/session failures.
                # Discord's own client can still retrieve the same public asset.
                read = getattr(asset, "read", None)
                if callable(read):
                    try:
                        async with asyncio.timeout(2):
                            avatar = await read()
                    except Exception as error:
                        self.report(error, "fantasy_avatar")
            return await image_work(render_soul_card, profile, member.display_name, avatar)

    async def weapon_bytes(self, profile):
        try:
            return await animation_work(render_weapon_acquisition, profile)
        except Exception as error:
            self.report(error, "fantasy_weapon_render")
            return None

    async def response(self, profile, member, owner):
        png = None
        try:
            png = await self.card_bytes(profile, member)
        except Exception as error:
            self.report(error, "fantasy_render")
        view = FantasyProfileView(self, owner, profile, member.display_name, image=bool(png))
        self.track_view(view)
        return soul_embed(profile, member.display_name, image=bool(png), bot=self.bot), view, png

    async def reveal(self, interaction, profile, member, owner, previous=None):
        if previous is not None:
            previous.finish()
        view = AwakeningRevealView(self, owner, profile, member)
        self.track_view(view)
        self.pending[owner] = view
        gif = None
        try:
            gif = await animation_work(render_ritual, profile)
        except Exception as error:
            self.report(error, "fantasy_reveal")
        try:
            embed = view.embed()
            if gif:
                embed.set_image(url="attachment://meyaya-ritual.gif")
            try:
                message = await interaction.edit_original_response(
                    content=None,
                    embed=embed,
                    view=view,
                    attachments=(
                        [discord.File(BytesIO(gif), filename="meyaya-ritual.gif")] if gif else []
                    ),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException:
                message = await interaction.edit_original_response(
                    content=None,
                    embed=view.embed(),
                    view=view,
                    attachments=[],
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            view.message = message
        except BaseException:
            view.finish()
            raise

    async def deliver(self, interaction, profile, member, owner, *, reveal=False, previous=None):
        from bot.data.fantasy_alignment import patron_for

        if (
            profile.user_id == owner
            and not getattr(profile, "is_meyaya_boss", False)
            and not patron_for(profile)
        ):
            reveal = True
        if reveal:
            await self.reveal(interaction, profile, member, owner, previous)
            return
        if previous is not None:
            previous.finish()
        embed, view, png = await self.response(profile, member, owner)
        try:
            files = [discord.File(BytesIO(png), filename="meyaya-soul.png")] if png else []
            try:
                message = await interaction.edit_original_response(
                    content=None,
                    embed=embed,
                    view=view,
                    attachments=files,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException:
                view.image = False
                embed = soul_embed(profile, member.display_name, bot=self.bot)
                try:
                    message = await interaction.edit_original_response(
                        content=None,
                        embed=embed,
                        view=view,
                        attachments=[],
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                except discord.HTTPException:
                    message = await interaction.followup.send(
                        embed=embed,
                        view=view,
                        wait=True,
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
            view.message = message
            # Component edits bypass TimedContext.send; retain the actual result
            # so replies to this image-only reveal still have useful context.
            outputs = getattr(self.bot, "_meyaya_command_outputs", None)
            if outputs is None:
                outputs = OrderedDict()
                self.bot._meyaya_command_outputs = outputs
            outputs[(message.channel.id, message.id)] = (
                monotonic(),
                CommandOutput(
                    "awaken",
                    owner,
                    member.display_name[:80],
                    json.dumps(result_summary(profile, member), ensure_ascii=False)[:2000],
                ),
            )
            while len(outputs) > 512:
                outputs.popitem(last=False)
        except BaseException:
            view.finish()
            raise

    @commands.hybrid_command(
        description="Replace your fantasy build after confirmation. Available once every 24 hours."
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def rebirth(self, ctx):
        await ctx.defer()
        if ctx.author.id in self.duel_users or ctx.author.id in self.pending:
            await ctx.send("Finish your current battle, awakening or rebirth first.")
            return
        await self.check_dungeon_activity(ctx.author.id)
        profile = await self.get_profile(ctx.author.id)
        if profile is None:
            await ctx.send("Your soul has not awakened yet. Use `/awaken` first.")
            return
        last = getattr(profile, "last_rebirth_at", None)
        if last and datetime.now(UTC) < utc(last) + REBIRTH_COOLDOWN:
            ready = int((utc(last) + REBIRTH_COOLDOWN).timestamp())
            await ctx.send(f"Your next rebirth is available <t:{ready}:R> (24-hour cooldown).")
            return
        # Recheck after the lookup await before reserving this user's confirmation.
        if ctx.author.id in self.duel_users or ctx.author.id in self.pending:
            await ctx.send("Finish your current fantasy activity first.")
            return
        view = RebirthView(self, ctx.author.id, profile)
        self.track_view(view)
        self.pending[ctx.author.id] = view
        safe = lambda value: discord.utils.escape_markdown(
            discord.utils.escape_mentions(str(value))
        )
        embed = meyaya_embed(
            "Rebirth · a new soul",
            f"Replace **{safe(profile.class_name)} / {safe(profile.affinity_name)}** and **{safe(profile.weapon_name)}**?\n\n"
            "Your class, base stats, weapon identity, abilities, guardian and alignment will be replaced across every server. "
            "A new random build is saved immediately and revealed at your pace. There is no undo.\n\n"
            "Total XP, Soul Level, Weapon Level, Highest Floor, rebirth count and battle history remain. "
            "Your new class receives your soul's existing level growth. Next rebirth: 24 hours after confirmation.",
            icon="✦",
        )
        try:
            view.message = await ctx.send(
                embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none()
            )
        except BaseException:
            view.finish()
            raise

    async def check_dungeon_activity(self, *user_ids):
        async with asyncio.timeout(10):
            async with self.bot.db_session() as session:
                repository = FantasyDungeonRepository(session)
                for user_id in user_ids:
                    if await repository.active(user_id):
                        raise commands.CommandError("Resume `/dungeon` and finish or abandon your active run first.")

    @commands.hybrid_command(description="Enter or resume the Tenfold Descent: ten worlds, one soul.")
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def dungeon(self, ctx):
        control = ""
        if getattr(ctx, "interaction", None) is None and getattr(ctx, "view", None) is not None:
            control = ctx.view.read_rest().strip().casefold()
        if control and (ctx.author.id != AYAYA_USER_ID or (ctx.prefix or "").strip().casefold() != "uwu"):
            await ctx.send(view=dungeon_notice("These dungeon controls are owner-only and use the `uwu` prefix."))
            return
        if control and control not in {"restart", "skip"}:
            await ctx.send(view=dungeon_notice("Use `uwu dungeon restart` or `uwu dungeon skip`."))
            return
        await ctx.defer()
        owner = ctx.author.id
        existing = self.duel_users.get(owner)
        if owner in self.pending or (existing is not None and not isinstance(existing, DungeonView)):
            await ctx.send(view=dungeon_notice("Finish your current fantasy activity before opening the descent."))
            return
        if len(self.duel_users) >= 32 and existing is None:
            await ctx.send(view=dungeon_notice("The arenas are busy. Try again shortly."))
            return
        async with asyncio.timeout(10):
            async with existing.lock if control and isinstance(existing, DungeonView) else nullcontext():
                try:
                    async with self.bot.db_session() as session:
                        service = DungeonService(session)
                        if control:
                            profile, run = await service.owner_control(owner, control, guild_id=ctx.guild.id)
                        else:
                            profile, run = await service.read(owner)
                except DungeonUnavailable as error:
                    await ctx.send(view=dungeon_notice(str(error)))
                    return
                if control and isinstance(existing, DungeonView):
                    existing.finish()
        if profile is None:
            await ctx.send(view=dungeon_notice("Use `/awaken` before beginning the descent."))
            return
        if profile.alignment not in {"meyaya", "veyra"} and not getattr(profile, "ending_route", None):
            await ctx.send(view=dungeon_notice("Choose your patron through `/fantasyprofile` first. Your oath matters here."))
            return
        # Revalidate admission after database awaits, then supersede old UI only.
        if owner in self.pending or (self.duel_users.get(owner) is not None and not isinstance(self.duel_users[owner], DungeonView)):
            await ctx.send(view=dungeon_notice("Finish your current fantasy activity first."))
            return
        if len(self.duel_users) >= 32 and owner not in self.duel_users:
            await ctx.send(view=dungeon_notice("The arenas are busy. Try again shortly."))
            return
        for old in tuple(self.views):
            if isinstance(old, DungeonView) and old.owner == owner:
                old.finish()
        view = DungeonView(self, owner, profile, run, guild_id=ctx.guild.id,
                           player_user=ctx.author, show_landing=not control)
        self.track_view(view)
        if run is None or run.phase != "complete":
            self.duel_users[owner] = view
        try:
            await view.deliver(ctx.send, initial=True)
            if control and isinstance(existing, DungeonView) and existing.message:
                try:
                    async with asyncio.timeout(5):
                        await existing.message.delete()
                except discord.NotFound:
                    pass
                except (discord.HTTPException, TimeoutError) as error:
                    self.report(error, "dungeon_owner_cleanup")
        except BaseException:
            view.finish()
            raise

    @commands.hybrid_command(description="Reveal the permanent fantasy identity hidden within you.")
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def awaken(self, ctx):
        await ctx.defer()
        if ctx.author.id in self.duel_users:
            await ctx.send("Finish your current battle before opening an awakening.")
            return
        if ctx.author.id in self.pending:
            await ctx.send(
                "Your awakening door is already open. Use its buttons, or wait for it to close."
            )
            return
        try:
            profile = await self.get_profile(ctx.author.id)
        except Exception as error:
            error_id = self.report(error, "fantasy_lookup")
            await ctx.send(
                f"The Soul Register is unavailable. Please try again later.\nError ID: `{error_id}`"
            )
            return
        if ctx.author.id in self.pending or ctx.author.id in self.duel_users:
            await ctx.send("Finish your current fantasy activity first.")
            return
        if profile is not None:
            view = AlreadyAwakenedView(self, ctx.author.id, profile, ctx.author)
            embed = meyaya_embed(
                "Your soul has already awakened",
                "The same identity follows you across servers until you choose `/rebirth`.\n\nOpen your Soul Interface below.",
                icon="✦",
            )
        else:
            view = AwakeningView(self, ctx.author.id)
            embed = meyaya_embed(
                "Something within you is stirring…",
                "*A dormant signature waits beyond the veil.*\n\nYour class, affinity, weapon and potential will become a **saved identity**. It stays until you choose `/rebirth` (24-hour cooldown).\n\n**Will you let it answer?**",
                icon="✦",
            )
            embed.set_footer(text="One soul · one awakening · every server")
        self.track_view(view)
        self.pending[ctx.author.id] = view
        try:
            view.message = await ctx.send(
                embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none()
            )
        except BaseException:
            view.finish()
            raise

    @commands.hybrid_command(description="View an awakened fantasy character.")
    @commands.cooldown(1, 8, commands.BucketType.user)
    async def fantasyprofile(self, ctx, member: FantasyProfileTarget | None = None):
        await ctx.defer()
        if isinstance(member, str) and member in {"meyaya", "veyra"}:
            from bot.services.meyaya_boss_renderer import render_patron_profile
            from bot.data.fantasy_alignment import PATRONS, PATRON_PROFILES
            from bot.views.fantasy import patron_profile_embed

            png = None
            try:
                async with self.render_slots:
                    png = await image_work(render_patron_profile, member)
            except Exception as error:
                self.report(error, "fantasy_patron_render")
            patron = PATRONS[member]
            lore = PATRON_PROFILES[member]
            remember_command_result(
                ctx,
                target_name=patron.name,
                title=patron.subtitle,
                class_name=lore["class"],
                affinity=lore["affinities"],
                status=lore["status"],
                threat=lore["threat"],
                lore=lore["lore"],
                quote=lore["quote"],
                weapon=lore["weapon"],
                method="Authored patron lore profile; hidden vitals, not a saved member identity.",
            )
            kwargs = dict(
                embed=patron_profile_embed(member, image=bool(png)),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            if png:
                kwargs["file"] = discord.File(BytesIO(png), filename="meyaya-soul.png")
            try:
                await ctx.send(**kwargs)
            except discord.HTTPException:
                if not png:
                    raise
                kwargs.pop("file", None)
                kwargs["embed"] = patron_profile_embed(member, image=False)
                await ctx.send(**kwargs)
            return
        member = member or ctx.author
        try:
            profile = await self.get_profile(member.id)
        except Exception as error:
            error_id = self.report(error, "fantasy_lookup")
            await ctx.send(
                f"The Soul Register is unavailable. Please try again later.\nError ID: `{error_id}`"
            )
            return
        if profile is None:
            await ctx.send(
                "Your soul hasn't awakened yet. Use `/awaken` when you're ready."
                if member.id == ctx.author.id
                else "Their soul hasn't awakened yet."
            )
            return
        from bot.data.fantasy_alignment import patron_for

        if (
            member.id == ctx.author.id
            and not getattr(profile, "is_meyaya_boss", False)
            and not patron_for(profile)
        ):
            view = AwakeningRevealView(self, ctx.author.id, profile, member)
            previous = self.pending.get(ctx.author.id)
            if previous:
                previous.finish()
            self.track_view(view)
            self.pending[ctx.author.id] = view
            try:
                view.message = await ctx.send(
                    embed=view.embed(), view=view, allowed_mentions=discord.AllowedMentions.none()
                )
            except BaseException:
                view.finish()
                raise
            return
        embed, view, png = await self.response(profile, member, ctx.author.id)
        remember_command_result(ctx, **result_summary(profile, member))
        kwargs = dict(embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none())
        try:
            if png:
                kwargs["file"] = discord.File(BytesIO(png), filename="meyaya-soul.png")
            try:
                view.message = await ctx.send(**kwargs)
            except discord.HTTPException:
                if not png:
                    raise
                kwargs.pop("file", None)
                view.image = False
                kwargs["embed"] = soul_embed(profile, member.display_name, bot=self.bot)
                remember_command_result(ctx, **result_summary(profile, member))
                view.message = await ctx.send(**kwargs)
        except BaseException:
            view.finish()
            raise


async def setup(bot):
    await bot.add_cog(FantasyCog(bot))
