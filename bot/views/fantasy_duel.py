"""Opponent consent, cancellable challenges and bounded participant-only results."""

import asyncio
from uuid import uuid4
import discord
from bot.utils.embeds import meyaya_embed


class DuelView(discord.ui.View):
    def __init__(self, cog, left, right, profiles, *, timeout=90):
        super().__init__(timeout=timeout)
        self.cog, self.left, self.right, self.profiles = cog, left, right, profiles
        self.owner = left.id
        self.participant_ids = (left.id, right.id)
        self.message = None
        self.lock = asyncio.Lock()
        self.closed = False
        self.task = None
        self.running = False
        self.token = uuid4().hex
        for index, child in enumerate(self.children):
            child.custom_id = f"meyaya:duel:{self.token}:{index}"

    async def interaction_check(self, interaction):
        if interaction.user.id in self.participant_ids:
            return True
        await interaction.response.send_message(
            "This duel belongs to its two fighters. Use `/versus` to challenge someone.",
            ephemeral=True,
        )
        return False

    def finish(self):
        self.closed = True
        for child in self.children:
            child.disabled = True
        self.stop()
        self.cog.release_view(self)
        for user_id in self.participant_ids:
            if self.cog.duel_users.get(user_id) is self:
                self.cog.duel_users.pop(user_id, None)
        if self.task and not self.task.done() and self.task is not asyncio.current_task():
            self.task.cancel()

    async def on_timeout(self):
        if self.running:
            return
        async with self.lock:
            if self.closed:
                return
            self.finish()
            if self.message:
                try:
                    if isinstance(self, DuelResultView):
                        await self.message.edit(view=self)
                    else:
                        await self.message.edit(
                            embed=meyaya_embed(
                                "Challenge expired",
                                "Neither identity was changed. Start another challenge with `/versus`.",
                                icon="⚔",
                            ),
                            view=self,
                        )
                except discord.HTTPException:
                    pass

    async def on_error(self, interaction, error, item):
        self.finish()
        error_id = self.cog.report(error, "fantasy_duel_ui")
        try:
            sender = (
                interaction.followup.send
                if interaction.response.is_done()
                else interaction.response.send_message
            )
            await sender(
                f"The duel was interrupted; both identities are safe. Error ID: `{error_id}`",
                ephemeral=True,
            )
        except discord.HTTPException:
            pass


class DuelChallengeView(DuelView):
    @discord.ui.button(label="Accept Duel", style=discord.ButtonStyle.success, emoji="⚔️")
    async def accept(self, interaction, button):
        if interaction.user.id != self.right.id:
            await interaction.response.send_message(
                "Only the challenged member can accept.", ephemeral=True
            )
            return
        await interaction.response.defer()
        if self.lock.locked():
            return
        async with self.lock:
            if self.closed or self.running:
                return
            self.running = True
            for child in self.children:
                child.disabled = True
            self.task = asyncio.current_task()
            try:
                async with asyncio.timeout(75):
                    await self.cog.run_duel(self, interaction)
            finally:
                self.finish()

    async def close_challenge(self, interaction, allowed_id, reason):
        if interaction.user.id != allowed_id:
            await interaction.response.send_message(
                "That decision belongs to the other fighter.", ephemeral=True
            )
            return
        await interaction.response.defer()
        if self.lock.locked():
            return
        async with self.lock:
            if self.closed or self.running:
                return
            self.finish()
            await interaction.edit_original_response(
                embed=meyaya_embed(
                    reason, "The arena stays quiet. Neither identity was changed.", icon="⚔"
                ),
                view=self,
            )

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.secondary)
    async def decline(self, interaction, button):
        await self.close_challenge(interaction, self.right.id, "Challenge declined")

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        await self.close_challenge(interaction, self.left.id, "Challenge cancelled")


class DuelResultView(DuelView):
    def __init__(self, cog, left, right, profiles, battle):
        super().__init__(cog, left, right, profiles, timeout=180)
        self.battle = battle
        self.rematching = False
        if getattr(profiles.get(right.id), "is_meyaya_boss", False):
            self.rematch.disabled = True
            self.rematch.label = "Rematch with /versus @Meyaya"

    @discord.ui.button(label="Rematch", style=discord.ButtonStyle.primary)
    async def rematch(self, interaction, button):
        if not await self.interaction_check(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        if self.lock.locked():
            return
        async with self.lock:
            if self.closed or self.rematching:
                return
            left = interaction.guild.get_member(interaction.user.id)
            other_id = self.right.id if interaction.user.id == self.left.id else self.left.id
            right = interaction.guild.get_member(other_id)
            if not left or not right:
                await interaction.followup.send(
                    "Both fighters must still be in this server.", ephemeral=True
                )
                return
            try:
                embed, view = await self.cog.create_duel(left, right)
            except Exception as error:
                from discord.ext import commands

                if not isinstance(error, commands.CommandError):
                    raise
                await interaction.followup.send(str(error), ephemeral=True)
                return
            try:
                view.message = await interaction.channel.send(
                    embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none()
                )
            except BaseException:
                view.finish()
                raise
            self.rematching = True
            button.disabled = True
            await interaction.message.edit(view=self)

    @discord.ui.button(label="My Fantasy Profile", style=discord.ButtonStyle.secondary)
    async def profile(self, interaction, button):
        if not await self.interaction_check(interaction):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        async with self.lock:
            if self.closed:
                return
            profile = await self.cog.get_profile(interaction.user.id)
            if profile is None:
                await interaction.followup.send(
                    "Use `/awaken` to awaken your soul first.", ephemeral=True
                )
                return
            embed, view, png = await self.cog.response(
                profile, interaction.user, interaction.user.id
            )
            try:
                from io import BytesIO

                kwargs = dict(embed=embed, view=view, ephemeral=True, wait=True)
                if png:
                    kwargs["file"] = discord.File(BytesIO(png), filename="meyaya-soul.png")
                try:
                    view.message = await interaction.followup.send(**kwargs)
                except discord.HTTPException:
                    if not png:
                        raise
                    from bot.views.fantasy import soul_embed

                    kwargs.pop("file", None)
                    view.image = False
                    kwargs["embed"] = soul_embed(
                        profile, interaction.user.display_name, bot=self.cog.bot
                    )
                    view.message = await interaction.followup.send(**kwargs)
            except BaseException:
                view.finish()
                raise

    @discord.ui.button(label="Battle Details", style=discord.ButtonStyle.secondary)
    async def details(self, interaction, button):
        if not await self.interaction_check(interaction):
            return
        from bot.services.fantasy_duel import element_multiplier, RULES_VERSION, MAX_ROUNDS

        battle = self.battle
        text = f"**{battle.verdict}**\n{battle.moves} moves · Round {battle.round}/{MAX_ROUNDS} · Rules v{RULES_VERSION}\nNo XP or permanent changes.\n"
        for f, other in ((battle.left, battle.right), (battle.right, battle.left)):
            name = discord.utils.escape_markdown(discord.utils.escape_mentions(f.name))
            if f.is_boss:
                text += f"\n**{name}**\nRecorded Class: SOULWEAVER\nAdaptive Class: {battle.boss_form}\nHP/MP: UNKNOWN\nPotential: ANALYSIS FAILED\nSpell Memory: {battle.memory_count} adaptations\nAuthority: Soul Interface\n"
                continue
            if other.is_boss:
                text += f"\n**{name}**\nCriticals: {f.critical_hits} · Dodges: {f.dodges} · Skills: {f.skills_used}\nHP {f.hp}/{f.max_hp} · MP {f.mp}/{f.max_mp}\n"
                continue
            text += f"\n**{name}**\nDamage dealt/taken: {f.damage_dealt}/{f.damage_taken}\nCriticals: {f.critical_hits} · Dodges: {f.dodges} · Skills: {f.skills_used}\nElement: {element_multiplier(f.affinity, other.affinity):.2f}× · Passive: {f.passive_name if f.passive else 'No mapped effect'}\n"
        await interaction.response.send_message(
            embed=meyaya_embed("Battle Details", text, icon="⚔"), ephemeral=True
        )
