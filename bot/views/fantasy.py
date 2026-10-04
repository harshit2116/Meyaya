"""Owner-checked confirmation and working read-only Soul Interface tabs."""

import asyncio
import logging

import discord

from bot.data.fantasy import RARITIES
from bot.logging.health import health
from bot.services.fantasy_render import theme_for
from bot.utils.application_emojis import application_emojis
from bot.utils.embeds import meyaya_embed
from bot.utils.loading import loading_indicator

logger = logging.getLogger(__name__)


def soul_embed(profile, name, *, tab="character", image=False, bot=None):
    theme = theme_for(profile)
    safe_name = discord.utils.escape_markdown(discord.utils.escape_mentions(name))[:100]
    embed = meyaya_embed(
        "Soul Interface",
        f"**{safe_name}** · {profile.fantasy_title}\n"
        f"{theme.symbol} {profile.affinity_name} · Level {profile.level}",
        color=int(theme.color[1:], 16),
        icon="✦",
    )
    if tab == "weapon":
        tier = RARITIES.index(profile.weapon_rarity) + 1 if profile.weapon_rarity in RARITIES else 1
        embed.add_field(
            name="Bound weapon",
            value=f"**{profile.weapon_name}**\n{profile.weapon_rarity} · {profile.weapon_type}\n{'◆'*tier}",
            inline=False,
        )
        embed.add_field(name="Its first promise", value=profile.weapon_lore, inline=False)
        embed.add_field(name="Resonance", value=profile.weapon_trait, inline=False)
    elif tab == "abilities":
        embed.add_field(
            name="Passive · " + profile.passive_name,
            value=profile.passive_description,
            inline=False,
        )
        embed.add_field(
            name="Signature · " + profile.signature_name,
            value=profile.signature_description,
            inline=False,
        )
        embed.add_field(
            name="Discipline", value=f"{profile.class_name} / {profile.subclass_name}", inline=False
        )
    elif tab == "details":
        embed.add_field(name="The dormant story", value=profile.description, inline=False)
        embed.add_field(name="Alignment", value=profile.alignment, inline=True)
        embed.add_field(
            name="Awakened", value=f"<t:{int(profile.awakened_at.timestamp())}:D>", inline=True
        )
        embed.add_field(
            name="Growth",
            value=f"Level {profile.level} · {profile.xp} XP\nOriginal identity follows this Discord user across servers.",
            inline=False,
        )
        embed.add_field(
            name="Original potential",
            value=" · ".join(
                f"{label} {profile.base_stats[key]}"
                for label, key in (
                    ("STR", "strength"),
                    ("DEX", "dexterity"),
                    ("INT", "intelligence"),
                    ("VIT", "vitality"),
                    ("LCK", "luck"),
                )
            ),
            inline=False,
        )
    else:
        if not image:
            embed.add_field(
                name="Awakened identity",
                value=f"**{profile.class_name}**\n{profile.subclass_name}\nHP {profile.hp}/{profile.max_hp} · MP {profile.mp}/{profile.max_mp}",
                inline=False,
            )
        embed.add_field(
            name="Potential",
            value=f"**STR** {profile.strength}  ·  **DEX** {profile.dexterity}  ·  **INT** {profile.intelligence}\n**VIT** {profile.vitality}  ·  **LCK** {profile.luck}",
            inline=False,
        )
        embed.add_field(
            name="Bound weapon",
            value=f"**{profile.weapon_name}**\n{profile.weapon_rarity} · {profile.weapon_type}",
            inline=False,
        )
        embed.add_field(
            name="Awakened arts",
            value=f"Passive · **{profile.passive_name}**\nSignature · **{profile.signature_name}**",
            inline=False,
        )
        reaction_icon = (
            next((str(e) for e in application_emojis(bot) if e.name == "meyaya_yay"), "✦")
            if bot
            else "✦"
        )
        embed.add_field(
            name=f"Meyaya {reaction_icon}", value=f"*“{profile.meyaya_reaction}”*", inline=False
        )
    if image:
        embed.set_image(url="attachment://meyaya-soul.png")
    embed.set_footer(text=theme.lore)
    return embed


class OwnedFantasyView(discord.ui.View):
    def __init__(self, cog, owner, *, timeout=180):
        super().__init__(timeout=timeout)
        self.cog, self.owner = cog, owner
        self.message = None
        self.lock = asyncio.Lock()
        self.closed = False

    async def interaction_check(self, interaction):
        if interaction.user.id == self.owner:
            return True
        await interaction.response.send_message(
            "This Soul Interface belongs to another viewer. Use `/fantasyprofile` to open your own.",
            ephemeral=True,
        )
        return False

    def disable(self):
        for button in self.children:
            button.disabled = True

    def finish(self):
        self.closed = True
        self.disable()
        self.stop()
        self.cog.release_view(self)

    async def on_timeout(self):
        async with self.lock:
            if self.closed:
                return
            self.finish()
            if self.message:
                try:
                    await self.message.edit(view=self)
                except discord.HTTPException:
                    pass

    async def on_error(self, interaction, error, item):
        error_id = health.capture(
            error,
            command="awaken",
            guild_id=interaction.guild_id,
            channel_id=interaction.channel_id,
            invocation="component",
            stage="fantasy_interface",
        )
        logger.warning(
            "fantasy_interface_failed error_id=%s exception=%s", error_id, type(error).__name__
        )
        try:
            await interaction.followup.send(
                f"I couldn't finish that step. Any saved identity remains safe; check `/fantasyprofile` before trying again.\nError ID: `{error_id}`",
                ephemeral=True,
            )
        except discord.HTTPException:
            pass


class FantasyProfileView(OwnedFantasyView):
    def __init__(self, cog, owner, profile, name, *, image=False):
        super().__init__(cog, owner)
        self.profile, self.name, self.image = profile, name, image
        self.tab = "character"
        for key, label in (
            ("character", "✦ Character"),
            ("weapon", "Weapon"),
            ("abilities", "Abilities"),
            ("details", "Details"),
        ):
            button = discord.ui.Button(
                label=label,
                style=(
                    discord.ButtonStyle.primary
                    if key == self.tab
                    else discord.ButtonStyle.secondary
                ),
            )

            async def callback(interaction, tab=key):
                await self.switch(interaction, tab)

            button.callback = callback
            button.tab = key
            self.add_item(button)

    async def switch(self, interaction, tab):
        await interaction.response.defer()
        if self.lock.locked():
            return
        async with self.lock:
            if self.closed:
                return
            embed = soul_embed(self.profile, self.name, tab=tab, image=self.image, bot=self.cog.bot)
            old = self.tab
            self.tab = tab
            for button in self.children:
                button.style = (
                    discord.ButtonStyle.primary
                    if button.tab == tab
                    else discord.ButtonStyle.secondary
                )
            try:
                await interaction.edit_original_response(
                    embed=embed, view=self, allowed_mentions=discord.AllowedMentions.none()
                )
            except BaseException:
                self.tab = old
                for button in self.children:
                    button.style = (
                        discord.ButtonStyle.primary
                        if button.tab == old
                        else discord.ButtonStyle.secondary
                    )
                raise


class AlreadyAwakenedView(OwnedFantasyView):
    def __init__(self, cog, owner, profile, member):
        super().__init__(cog, owner)
        self.profile, self.member = profile, member

    @discord.ui.button(label="View Character", style=discord.ButtonStyle.primary)
    async def character(self, interaction, button):
        await interaction.response.defer()
        if self.lock.locked():
            return
        async with self.lock:
            if self.closed:
                return
            async with loading_indicator(interaction.channel, self.cog.bot):
                await self.cog.deliver(
                    interaction, self.profile, self.member, self.owner, previous=self
                )
            self.finish()


class AwakeningView(OwnedFantasyView):
    @discord.ui.button(label="Awaken", style=discord.ButtonStyle.primary, emoji="🌸")
    async def awaken(self, interaction, button):
        await interaction.response.defer()
        if self.lock.locked():
            return
        async with self.lock:
            if self.closed:
                return
            self.disable()
            try:
                async with loading_indicator(interaction.channel, self.cog.bot):
                    profile, created = await self.cog.awaken_user(self.owner)
                    # Save succeeded before any animated stages or avatar fetch.
                    await self.cog.deliver(
                        interaction,
                        profile,
                        interaction.user,
                        self.owner,
                        reveal=created,
                        previous=self,
                    )
            finally:
                if not self.closed:
                    self.finish()
                    if self.message:
                        try:
                            await self.message.edit(view=self)
                        except discord.HTTPException:
                            pass

    @discord.ui.button(label="Not yet", style=discord.ButtonStyle.secondary)
    async def decline(self, interaction, button):
        await interaction.response.defer()
        if self.lock.locked():
            return
        async with self.lock:
            if self.closed:
                return
            self.finish()
            await interaction.edit_original_response(
                content="The door stays quiet. Come back when you're ready.", embed=None, view=self
            )
