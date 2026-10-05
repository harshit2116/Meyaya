"""Owner-checked confirmation and working read-only Soul Interface tabs."""

import asyncio
import logging
from io import BytesIO

import discord

from bot.data.fantasy import RARITIES
from bot.logging.health import health
from bot.services.fantasy_render import theme_for
from bot.utils.application_emojis import application_emojis
from bot.utils.embeds import meyaya_embed
from bot.utils.loading import loading_indicator
from bot.data.fantasy_alignment import PATRONS, patron_for, ALIGNMENT_ART
from bot.services.fantasy_profile import AlignmentUnavailable

logger = logging.getLogger(__name__)


def soul_embed(profile, name, *, tab="character", image=False, bot=None):
    if getattr(profile, "is_meyaya_boss", False):
        if image:
            return discord.Embed().set_image(url="attachment://meyaya-soul.png")
        embed = meyaya_embed(
            "Soul Interface",
            "# MEYAYA\nThe Girl at the End of Every Story",
            color=0xEEB4E4,
            icon="✦",
        )
        for label, value in (
            ("Recorded Class", "SOULWEAVER"),
            ("Current Class", "[ REWRITING... ]"),
            ("Affinity", "ARCANE · BLOOM · EGO"),
            ("Potential", "ANALYSIS FAILED"),
            ("Soul Pressure", "UNREADABLE"),
            ("Bound Weapon", profile.weapon_name + "\nMythic · Spellcrown"),
            (
                "Awakened Arts",
                "Passive - Spell Memory\nSignature - Prism Cascade\nAuthority - Soul Interface",
            ),
            ("Vitals", "HP ??? / ???\nMP ??? / ???"),
            ("Threat", "BEYOND MEASUREMENT"),
        ):
            embed.add_field(name=label, value=value, inline=False)
        if image:
            embed.set_image(url="attachment://meyaya-soul.png")
        embed.set_footer(text="An unwritten spell has chosen its author.")
        return embed
    theme = theme_for(profile)
    safe_name = discord.utils.escape_markdown(discord.utils.escape_mentions(name))[:100]
    embed = meyaya_embed(
        "Soul Interface",
        f"**{safe_name}** · {profile.fantasy_title}\n"
        f"{theme.symbol} {profile.affinity_name} · Level {profile.level}",
        color=int(theme.color[1:], 16),
        icon="✦",
    )
    embed.add_field(
        name="Rebirths", value=str(getattr(profile, "rebirth_count", 0) or 0), inline=True
    )
    patron = patron_for(profile)
    if patron:
        embed.add_field(
            name="Alignment",
            value=f"{patron.icon} **{patron.name} - {patron.subtitle}**\n{patron.oath}",
            inline=False,
        )
        embed.add_field(name=patron.resonance, value=patron.effect, inline=False)
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
        from bot.services.fantasy_guardian import bound_guardian

        companion = bound_guardian(profile)
        embed.add_field(
            name="Soul-bound guardian",
            value=f"{companion.name} · {companion.affinity_name}\nView `/guardian` · Battle `/guardianbattle`",
            inline=False,
        )
        embed.add_field(name="The dormant story", value=profile.description, inline=False)
        if not patron:
            embed.add_field(
                name="Alignment",
                value="Unclaimed - choose through your own `/fantasyprofile`.",
                inline=False,
            )
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
            name=f"{patron.name if patron else 'Meyaya'} {patron.icon if patron else reaction_icon}",
            value=f"*“{profile.meyaya_reaction}”*",
            inline=False,
        )
    if image:
        embed.set_image(url="attachment://meyaya-soul.png")
    embed.set_footer(text=theme.lore)
    return embed


class OwnedFantasyView(discord.ui.View):
    command_name = "awaken"

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
            command=self.command_name,
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
        if getattr(profile, "is_meyaya_boss", False):
            # Her dedicated artwork is the whole profile, with no redundant tabs.
            return
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


class AwakeningRevealView(OwnedFantasyView):
    """Saved identity revealed at the owner's pace, never on a timer."""

    LABELS = ("Reveal weapon", "Choose your alignment", "Choose a presence below")

    def __init__(self, cog, owner, profile, member):
        super().__init__(cog, owner, timeout=300)
        self.profile, self.member = profile, member
        self.step = 0
        self.weapon_gif = None
        self.refresh_buttons()

    def refresh_buttons(self):
        self.advance.label = self.LABELS[self.step]
        self.back.disabled = self.step == 0
        self.clear_items()
        if self.step < 2:
            self.add_item(self.advance)
        if self.step == 2:
            self.add_item(self.origin)
            self.add_item(self.erasure)
        self.add_item(self.back)

    def finish(self):
        self.weapon_gif = None
        super().finish()

    def embed(self):
        profile = self.profile
        theme = theme_for(profile)
        if self.step == 2:
            embed = meyaya_embed(
                "A Call Beyond the Soul Interface",
                "Two presences have turned toward your awakening.\n"
                "One offers **Origin**. One offers **Erasure**.\n\n"
                "**Choose who claims this life. Your oath is locked until rebirth.**\n"
                "Your class, affinity and weapon remain your own.",
                color=0xF7B0D5,
                icon="✦",
            )
            embed.set_footer(
                text="Discovery 3/3 · Your choice saves before the final profile is revealed"
            )
            return embed
        embed = meyaya_embed(
            "Your awakening",
            "Take your time. Each discovery stays until you continue.",
            color=int(theme.color[1:], 16),
            icon="✦",
        )
        if self.step == 1:
            embed.title = "✦ You received this weapon"
            embed.description = "Your weapon has answered. It is now bound to your saved identity."
        embed.add_field(
            name="Affinity", value=f"{theme.symbol} **{profile.affinity_name}**", inline=False
        )
        if self.step >= 1:
            embed.add_field(
                name="Bound weapon",
                value=f"**{profile.weapon_name}**\n{profile.weapon_rarity} · {profile.weapon_type}\n{profile.weapon_lore}",
                inline=False,
            )
        embed.set_footer(
            text=f"Discovery {self.step + 1}/3 · Saved until rebirth · /fantasyprofile resumes it anytime"
        )
        return embed

    async def move(self, interaction, direction):
        await interaction.response.defer()
        if self.lock.locked():
            return
        async with self.lock:
            if self.closed:
                return
            old = self.step
            self.step = max(0, min(2, self.step + direction))
            self.refresh_buttons()
            try:
                async with loading_indicator(interaction.channel, self.cog.bot):
                    if self.step == 1 and self.weapon_gif is None:
                        self.weapon_gif = await self.cog.weapon_bytes(self.profile)
                    embed = self.embed()
                    files = []
                    if self.step == 1 and self.weapon_gif:
                        embed.set_image(url="attachment://meyaya-weapon.gif")
                        files = [
                            discord.File(BytesIO(self.weapon_gif), filename="meyaya-weapon.gif")
                        ]
                    elif self.step == 2 and ALIGNMENT_ART.is_file():
                        embed.set_image(url="attachment://origin-erasure.png")
                        files = [discord.File(str(ALIGNMENT_ART), filename="origin-erasure.png")]
                    try:
                        await interaction.edit_original_response(
                            content=None,
                            embed=embed,
                            attachments=files,
                            view=self,
                            allowed_mentions=discord.AllowedMentions.none(),
                        )
                    except discord.HTTPException as error:
                        if not files:
                            raise
                        self.cog.report(error, "fantasy_reveal_upload")
                        await interaction.edit_original_response(
                            content=None,
                            embed=self.embed(),
                            attachments=[],
                            view=self,
                            allowed_mentions=discord.AllowedMentions.none(),
                        )
            except BaseException:
                self.step = old
                self.refresh_buttons()
                raise

    @discord.ui.button(label="Reveal weapon", style=discord.ButtonStyle.primary)
    async def advance(self, interaction, button):
        await self.move(interaction, 1)

    @discord.ui.button(
        label="Previous discovery", style=discord.ButtonStyle.secondary, disabled=True
    )
    async def back(self, interaction, button):
        await self.move(interaction, -1)

    async def choose(self, interaction, choice):
        # Enforce ownership even when invoked outside discord.py's dispatch.
        if not await self.interaction_check(interaction):
            return
        await interaction.response.defer()
        if self.lock.locked():
            return
        async with self.lock:
            if self.closed or self.step != 2:
                return
            try:
                async with loading_indicator(interaction.channel, self.cog.bot):
                    self.profile = await self.cog.align_user(
                        self.owner, self.profile.awakened_at, choice
                    )
                    # Transaction has committed. A failed render never changes this oath.
                    await self.cog.deliver(
                        interaction, self.profile, self.member, self.owner, previous=self
                    )
            except AlignmentUnavailable as error:
                await interaction.followup.send(str(error), ephemeral=True)

    @discord.ui.button(
        label="Answer Meyaya - Bloom of Origin", emoji="🌸", style=discord.ButtonStyle.primary
    )
    async def origin(self, interaction, button):
        await self.choose(interaction, "meyaya")

    @discord.ui.button(
        label="Answer Veyra - Enemy of All", emoji="🩸", style=discord.ButtonStyle.danger
    )
    async def erasure(self, interaction, button):
        await self.choose(interaction, "veyra")


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
