"""Permanent awakenings: database first, bounded visual reveal second."""

import asyncio
import json
import logging
import secrets
from collections import OrderedDict
from io import BytesIO
from time import monotonic
from types import SimpleNamespace
from bot.services.fantasy_boss import meyaya_boss_profile
from bot.services.meyaya_boss_combat import BossDuelEngine, public_fighter
from bot.services.meyaya_boss_presentation import BossPresentation
from bot.utils.fantasy_profile_target import FantasyProfileTarget

import discord
from discord.ext import commands

from bot.logging.health import health
from bot.services.fantasy_profile import FantasyProfileService, REBIRTH_COOLDOWN, utc
from datetime import UTC, datetime
from bot.views.fantasy_rebirth import RebirthView
from bot.services.fantasy_render import render_ritual, render_soul_card
from bot.services.fantasy_weapon_render import render_weapon_acquisition
from bot.services.fantasy_duel import DuelEngine, Fighter, RULES_VERSION
from bot.services.fantasy_duel_renderer import render_duel
from bot.repositories.fantasy_duels import FantasyDuelRepository
from bot.views.fantasy_duel import DuelChallengeView, DuelResultView
from bot.services.fantasy_guardian import bound_guardian
from bot.services.guardian_render import guardian_card
from bot.views.guardian_battle import GuardianChallengeView, GuardianBattleView
from bot.services.fantasy_guardian import GuardianBattle, GuardianFighter
from bot.utils.command_context import CommandOutput, remember_command_result
from bot.utils.embeds import meyaya_embed
from bot.utils.image_work import BoundedImageGate, image_work
from bot.views.fantasy import (
    AlreadyAwakenedView,
    AwakeningView,
    AwakeningRevealView,
    FantasyProfileView,
    soul_embed,
)

logger = logging.getLogger(__name__)
MAX_VIEWS = 64


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
        self.render_slots = BoundedImageGate(capacity=3)

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
        profiles = {
            left.id: await self.get_profile(left.id),
            right.id: await self.get_profile(right.id),
        }
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
        is_boss = view.right.id == getattr(getattr(self.bot, "user", None), "id", None)
        engine_type = BossDuelEngine if is_boss else DuelEngine
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
        cinematic = BossPresentation(self, view, interaction.channel) if is_boss else None
        try:
            view.message = await interaction.edit_original_response(
                embed=meyaya_embed(
                    "The author accepts" if is_boss else "Challenge accepted",
                    (
                        "The Soul Interface's author accepts your challenge. Your awakening stays untouched."
                        if is_boss
                        else "The versus image, live battle and result will appear below. Both saved identities remain unchanged."
                    ),
                    icon="⚔",
                ),
                view=view,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            for member in (view.left, view.right):
                try:
                    async with asyncio.timeout(8):
                        visual = await self.bot.build_profile_aesthetic_service().inspect(member)
                    portraits.append(visual.avatar or b"")
                    palettes.append(visual.palette)
                except Exception as error:
                    self.report(error, "fantasy_duel_palette")
                    portraits.append(b"")
                    palettes.append(())
            if cinematic:
                await cinematic.intro(state)

            async def frame(*, intro=False, outcome=False, controls=None, history_note=""):
                nonlocal battle_message
                if any(
                    view.left.guild.get_member(user_id) is None for user_id in view.participant_ids
                ):
                    raise commands.CommandError("A fighter left this server.")
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
                        f"✦ Soulweaver → **{safe(state.boss_form)}** · Soul Pressure: UNREADABLE"
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
                embed.set_footer(text=f"{state.arena[0]} · Temporary combat · identities unchanged")
                png = None
                try:
                    async with self.render_slots:
                        png = await image_work(
                            render_duel, state, tuple(portraits), tuple(palettes), intro=intro
                        )
                except Exception as error:
                    self.report(error, "fantasy_duel_render")
                if png:
                    embed.set_image(url="attachment://meyaya-duel.png")
                # The opening is a full-size attachment, not a thumbnail embed.
                # Keep the intro separate; only the dedicated battle message changes.
                kwargs = dict(
                    content=history_note if outcome and png and history_note else None,
                    embed=None if (intro or outcome) and png else embed,
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
                    message = await deliver_frame()
                except discord.HTTPException:
                    if not png:
                        raise
                    embed.set_image(url=None)
                    kwargs["embed"] = embed
                    kwargs["attachments"] = []
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
                if cinematic and not state.finished:
                    await cinematic.speak(state)
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
                    encounter="meyaya_boss",
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
            result_view = DuelResultView(self, view.left, view.right, view.profiles, state)
            result_view.task = view.task
            # Replace the consent controller rather than requiring an extra view slot.
            self.release_view(view)
            self.track_view(result_view)
            if cinematic:
                await cinematic.finish(state)
                result_view.cinematic_message = cinematic.message
            result_view.message = await frame(outcome=True, controls=result_view, history_note=note)
            outputs = getattr(self.bot, "_meyaya_command_outputs", None)
            if outputs is None:
                outputs = self.bot._meyaya_command_outputs = OrderedDict()
            message = result_view.message
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

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        for view in tuple(self.views):
            if (
                member.id in getattr(view, "participant_ids", ())
                and view.left.guild.id == member.guild.id
            ):
                view.finish()

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        for view in tuple(self.views):
            if getattr(getattr(getattr(view, "left", None), "guild", None), "id", None) == guild.id:
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
    async def versus(self, ctx, member: discord.Member):
        await ctx.defer()
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
                    async with asyncio.timeout(75):
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

    @commands.hybrid_command(description="Challenge a member to a turn-based guardian battle.")
    @commands.guild_only()
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def guardianbattle(self, ctx, member: discord.Member):
        await ctx.defer()
        _, previous = await self.create_duel(ctx.author, member)
        if member.id == getattr(getattr(self.bot, "user", None), "id", None):
            battle = GuardianBattle(
                GuardianFighter(
                    bound_guardian(previous.profiles[ctx.author.id]), ctx.author.display_name
                ),
                GuardianFighter(bound_guardian(previous.profiles[member.id]), member.display_name),
                secrets.randbits(63),
            )
            view = GuardianBattleView(self, ctx.author, member, previous.profiles, battle)
            previous.finish()
            self.track_view(view)
            self.duel_users[ctx.author.id] = view
            view.task = asyncio.current_task()
            try:
                async with asyncio.timeout(25):
                    await ctx.send(
                        "Meyaya accepts with her overpowered Astral Dragon. Her moves are automatic; yours are manual. No rewards or permanent changes.",
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                    await view.update(SimpleNamespace(channel=ctx.channel), initial=True)
                view.schedule_turn()
            except BaseException:
                view.finish()
                raise
            return
        view = GuardianChallengeView(self, ctx.author, member, previous.profiles)
        previous.finish()
        self.track_view(view)
        for user_id in view.participant_ids:
            self.duel_users[user_id] = view
        guardians = [bound_guardian(view.profiles[m.id]) for m in (view.left, view.right)]
        embed = meyaya_embed(
            "Guardian battle challenge",
            f"{ctx.author.mention} and {member.mention}\n**{guardians[0].name}** vs **{guardians[1].name}**\nOnly the challenged trainer can accept. Choose your own moves in this channel.\n60 seconds per turn · temporary HP/MP",
            icon="✦",
        )
        embed.set_footer(text="Challenge expires in 90 seconds · requires saved awakenings")
        remember_command_result(
            ctx,
            challenger_id=ctx.author.id,
            opponent_id=member.id,
            status="Guardian challenge awaiting consent.",
        )
        try:
            view.message = await ctx.send(
                embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none()
            )
        except BaseException:
            view.finish()
            raise

    async def card_bytes(self, profile, member):
        async with self.render_slots:
            if getattr(profile, "is_meyaya_boss", False):
                return await image_work(render_soul_card, profile, member.display_name)
            avatar = b""
            try:
                asset = member.display_avatar.with_size(512).with_format("png")
                avatar = await self.bot.build_profile_aesthetic_service()._download(str(asset))
            except Exception as error:
                # A portrait outage must not stop an already saved identity.
                self.report(error, "fantasy_avatar")
            return await image_work(render_soul_card, profile, member.display_name, avatar)

    async def weapon_bytes(self, profile):
        try:
            async with self.render_slots:
                return await image_work(render_weapon_acquisition, profile)
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
            async with self.render_slots:
                gif = await image_work(render_ritual, profile)
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
            "Your class, stats, weapon, abilities, guardian and progression will be replaced across every server. "
            "A new random build is saved immediately and revealed at your pace. There is no undo.\n\n"
            "Your rebirth count and existing battle history remain. Next rebirth: 24 hours after confirmation.",
            icon="✦",
        )
        try:
            view.message = await ctx.send(
                embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none()
            )
        except BaseException:
            view.finish()
            raise

    @commands.hybrid_command(description="Reveal the permanent fantasy identity hidden within you.")
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def awaken(self, ctx):
        await ctx.defer()
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

            async with self.render_slots:
                png = await image_work(render_patron_profile, member)
            name = "Veyra" if member == "veyra" else "Meyaya"
            remember_command_result(
                ctx,
                target_name=name,
                title="Enemy of All" if member == "veyra" else "Bloom of Origin",
                class_name="Void Revenant" if member == "veyra" else "Star-Petal Arcanist",
                weapon=(
                    "Mournfang - Blade of the Last Silence"
                    if member == "veyra"
                    else "Everbloom - Crown of the Last Wish"
                ),
                method="Authored patron lore profile; hidden vitals, not a saved member identity.",
            )
            await ctx.send(
                embed=discord.Embed().set_image(url="attachment://meyaya-soul.png"),
                file=discord.File(BytesIO(png), filename="meyaya-soul.png"),
                allowed_mentions=discord.AllowedMentions.none(),
            )
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
