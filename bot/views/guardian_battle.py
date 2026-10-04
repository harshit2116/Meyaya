"""Consent and alternating trainer choices, using FantasyCog's bounded admission."""

import asyncio
from io import BytesIO
from time import monotonic
import secrets
import json
from collections import OrderedDict
import discord
from bot.services.fantasy_guardian import bound_guardian, GuardianFighter, GuardianBattle
from bot.services.guardian_render import battle_card
from bot.utils.image_work import image_work
from bot.utils.embeds import meyaya_embed
from bot.views.fantasy_duel import DuelView, DuelChallengeView
from bot.utils.command_context import CommandOutput


def safe(text):
    return discord.utils.escape_markdown(discord.utils.escape_mentions(str(text)))


class GuardianAccess:
    async def interaction_check(self, interaction):
        if interaction.user.id in self.participant_ids and not self.closed:
            return True
        await interaction.response.send_message(
            "This guardian arena is closed or belongs to other trainers. Use `/guardianbattle` to start yours.",
            ephemeral=True,
        )
        return False


class GuardianChallengeView(GuardianAccess, DuelChallengeView):
    @discord.ui.button(label="Accept Guardian Battle", style=discord.ButtonStyle.success)
    async def accept(self, interaction, button):
        if interaction.user.id != self.right.id:
            await interaction.response.send_message(
                "Only the challenged trainer can accept.", ephemeral=True
            )
            return
        await interaction.response.defer()
        if self.lock.locked():
            return
        async with self.lock:
            if self.closed:
                return
            battle = GuardianBattle(
                *(
                    GuardianFighter(bound_guardian(self.profiles[m.id]), m.display_name)
                    for m in (self.left, self.right)
                ),
                secrets.randbits(63),
            )
            view = GuardianBattleView(self.cog, self.left, self.right, self.profiles, battle)
            self.finish()
            self.cog.track_view(view)
            for user_id in view.participant_ids:
                self.cog.duel_users[user_id] = view
            view.task = asyncio.current_task()
            try:
                async with asyncio.timeout(25):
                    await interaction.edit_original_response(
                        embed=meyaya_embed(
                            "Guardian challenge accepted",
                            "Follow the guardians' battle below. Your awakening is unchanged.",
                            icon="✦",
                        ),
                        view=self,
                    )
                    await view.update(interaction, initial=True)
                view.schedule_turn()
            except BaseException:
                view.finish()
                raise


class GuardianBattleView(GuardianAccess, DuelView):
    def __init__(self, cog, left, right, profiles, battle):
        # The explicit turn/arena timer owns expiry, including time spent on
        # NPC rendering. A second Discord view timeout could disable controls
        # before the player's actual turn deadline.
        super().__init__(cog, left, right, profiles, timeout=None)
        self.battle = battle
        self.timer = None
        self.deadline = monotonic() + 360
        self.turn_deadline = monotonic() + 60
        self.refresh_buttons()

    def finish(self):
        if self.timer:
            self.timer.cancel()
        super().finish()

    def refresh_buttons(self):
        npc_turn = getattr(self.profiles.get(self.battle.actor.guardian.owner_id), "is_meyaya_boss", False)
        for index, child in enumerate(self.children):
            child.custom_id = f"meyaya:duel:{self.token}:{index}:{self.battle.moves}"
            child.disabled = self.battle.finished
            if npc_turn and not child.label.startswith("Recall"):
                child.disabled = True
            if child.label.startswith("Affinity"):
                child.disabled |= self.battle.actor.mp < 14
            if child.label.startswith("Blessing"):
                actor = self.battle.actor
                child.label = f"Blessing · {2 - actor.blessing_uses} left · 18 MP"
                child.disabled |= not actor.can_bless()

    def schedule_turn(self):
        if self.timer:
            self.timer.cancel()
        self.turn_deadline = min(self.deadline, monotonic() + 60)
        if getattr(self.profiles.get(self.battle.actor.guardian.owner_id), "is_meyaya_boss", False):
            self.timer = asyncio.get_running_loop().call_later(1.2, self.launch_npc)
            return
        self.timer = asyncio.get_running_loop().call_later(
            max(0, self.turn_deadline - monotonic()), self.launch_expiry
        )

    def launch_npc(self):
        if not self.closed:
            self.task = asyncio.create_task(self.npc_move())
            self.task.add_done_callback(lambda task: None if task.cancelled() else task.exception())

    async def npc_move(self):
        async with self.lock:
            if self.closed or self.battle.finished:
                return
            if monotonic() >= self.deadline:
                # Let the usual expiry path acquire the lock itself.
                self.timer = asyncio.get_running_loop().call_later(0, self.launch_expiry)
                return
            actor = self.battle.actor
            if not getattr(self.profiles.get(actor.guardian.owner_id), "is_meyaya_boss", False):
                return
            move = "blessing" if actor.hp < actor.guardian.max_hp * 0.7 and actor.can_bless() else "affinity" if actor.mp >= 14 else "strike"
            try:
                self.battle.choose(actor.guardian.owner_id, move)
                async with asyncio.timeout(25):
                    await self.update(None)
                if self.battle.finished:
                    self.finish()
                else:
                    self.schedule_turn()
            except Exception as error:
                self.finish()
                self.cog.report(error, "guardian_duel_npc")

    def launch_expiry(self):
        if not self.closed:
            self.task = asyncio.create_task(self.expire())
            self.task.add_done_callback(lambda task: None if task.cancelled() else task.exception())

    async def expire(self):
        async with self.lock:
            if self.closed or self.battle.finished:
                return
            self.battle.finished = True
            if monotonic() >= self.deadline:
                left, right = self.battle.fighters
                delta = left.hp / left.guardian.max_hp - right.hp / right.guardian.max_hp
                self.battle.winner_id = (
                    None if abs(delta) <= 0.03 else (left if delta > 0 else right).guardian.owner_id
                )
                self.battle.log = (
                    "The six-minute arena limit was reached. Remaining HP percentage decides."
                )
            else:
                self.battle.winner_id = self.battle.fighters[1 - self.battle.turn].guardian.owner_id
                self.battle.log = f"{self.battle.actor.owner_name} ran out of turn time. The opposing guardian wins."
            self.finish()
            try:
                if self.message:
                    async with asyncio.timeout(15):
                        await self.update(None)
            except Exception as error:
                self.cog.report(error, "guardian_duel_timeout")

    async def on_timeout(self):
        # Fixed deadlines cannot be extended by outsiders or repeated invalid clicks.
        if monotonic() >= self.turn_deadline:
            await self.expire()

    async def update(self, interaction, *, initial=False):
        self.refresh_buttons()
        b = self.battle
        text = "\n".join(
            f"**{safe(f.owner_name)}** · {f.guardian.name}\nHP {f.hp}/{f.guardian.max_hp} · MP {f.mp}/{f.guardian.max_mp}"
            for f in b.fighters
        )
        text += "\n\n" + safe(b.log)
        if b.finished:
            winner = next(
                (f.owner_name for f in b.fighters if f.guardian.owner_id == b.winner_id), None
            )
            text += f"\n\n**{safe(winner)} won!**" if winner else "\n\n**Draw.**"
        else:
            npc = getattr(self.profiles.get(b.actor.guardian.owner_id), "is_meyaya_boss", False)
            text += f"\n\n**{safe(b.actor.owner_name)}'s turn** · " + ("choosing automatically…" if npc else "choose a move.")
        embed = meyaya_embed("Guardian Arena", text, icon="✦")
        if not b.finished:
            embed.add_field(
                name="Choose your move",
                value=f"**Strike:** free attack\n**Affinity Pulse:** elemental attack · 14 MP\n**Guard:** halves the next hit · restores 8 MP\n**{b.actor.guardian.blessing}:** {b.actor.guardian.blessing_text} · 18 MP · two uses per match",
                inline=False,
            )
        embed.set_footer(
            text="60 seconds per turn · 24 moves / 6 minutes maximum · no permanent changes"
        )
        data = None
        try:
            async with self.cog.render_slots:
                data = await image_work(battle_card, b)
        except Exception as error:
            self.cog.report(error, "guardian_duel_render")
        if data:
            embed.set_image(url="attachment://guardian-battle.png")
        kwargs = dict(embed=embed, view=self, allowed_mentions=discord.AllowedMentions.none())

        async def deliver():
            if initial:
                return await interaction.channel.send(
                    **kwargs,
                    files=(
                        [discord.File(BytesIO(data), filename="guardian-battle.png")]
                        if data
                        else []
                    ),
                )
            return await self.message.edit(
                **kwargs,
                attachments=(
                    [discord.File(BytesIO(data), filename="guardian-battle.png")] if data else []
                ),
            )

        try:
            self.message = await deliver()
        except discord.HTTPException:
            if not data:
                raise
            data = None
            embed.set_image(url=None)
            self.message = await deliver()

        outputs = getattr(self.cog.bot, "_meyaya_command_outputs", None)
        if outputs is None:
            outputs = self.cog.bot._meyaya_command_outputs = OrderedDict()
        summary = dict(
            moves=b.moves,
            winner_id=b.winner_id,
            finished=b.finished,
            last_move=b.log,
            fighters=[
                dict(
                    owner_id=f.guardian.owner_id,
                    owner_name=f.owner_name[:80],
                    guardian=f.guardian.name,
                    affinity=f.guardian.affinity_name,
                    hp=f.hp,
                    max_hp=f.guardian.max_hp,
                    mp=f.mp,
                    max_mp=f.guardian.max_mp,
                )
                for f in b.fighters
            ],
            method="Manual local guardian battle; no permanent fantasy changes.",
        )
        outputs[(self.message.channel.id, self.message.id)] = (
            monotonic(),
            CommandOutput(
                "guardianbattle",
                self.owner,
                self.left.display_name[:80],
                json.dumps(summary, ensure_ascii=False)[:2000],
            ),
        )
        while len(outputs) > 512:
            outputs.popitem(last=False)

    async def play(self, interaction, move):
        if not await self.interaction_check(interaction):
            return
        await interaction.response.defer()
        if self.lock.locked():
            await interaction.followup.send("The last move is still resolving.", ephemeral=True)
            return
        if monotonic() >= self.turn_deadline:
            await self.expire()
            return
        async with self.lock:
            if self.closed:
                return
            custom_id = (getattr(interaction, "data", None) or {}).get("custom_id")
            if custom_id and not custom_id.endswith(f":{self.battle.moves}"):
                await interaction.followup.send(
                    "That button belongs to an older turn. Use the current battle controls.",
                    ephemeral=True,
                )
                return
            try:
                if move == "forfeit" and getattr(self.profiles.get(self.battle.actor.guardian.owner_id), "is_meyaya_boss", False):
                    self.battle.finished = True
                    self.battle.winner_id = self.battle.actor.guardian.owner_id
                    self.battle.log = f"{self.left.display_name} recalled their guardian. Meyaya wins."
                else:
                    self.battle.choose(interaction.user.id, move)
            except ValueError as error:
                await interaction.followup.send(str(error), ephemeral=True)
                return
            self.task = asyncio.current_task()
            if self.timer:
                self.timer.cancel()
            try:
                async with asyncio.timeout(25):
                    await self.update(interaction)
                if self.battle.finished:
                    self.finish()
                else:
                    self.schedule_turn()
            except BaseException:
                self.finish()
                raise

    @discord.ui.button(label="Strike", style=discord.ButtonStyle.primary, row=0)
    async def strike(self, interaction, button):
        await self.play(interaction, "strike")

    @discord.ui.button(label="Affinity Pulse · 14 MP", style=discord.ButtonStyle.primary, row=0)
    async def affinity(self, interaction, button):
        await self.play(interaction, "affinity")

    @discord.ui.button(label="Guard · +8 MP", style=discord.ButtonStyle.secondary, row=1)
    async def guard(self, interaction, button):
        await self.play(interaction, "guard")

    @discord.ui.button(label="Blessing · 18 MP", style=discord.ButtonStyle.success, row=1)
    async def blessing(self, interaction, button):
        await self.play(interaction, "blessing")

    @discord.ui.button(label="Recall / Forfeit", style=discord.ButtonStyle.danger, row=2)
    async def recall(self, interaction, button):
        await self.play(interaction, "forfeit")
