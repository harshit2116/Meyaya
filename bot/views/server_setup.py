"""Manager-only setup wizard. Nothing changes until Save is clicked."""

import asyncio
import logging

import discord
from bot.utils.components_v2 import MeyayaView
from sqlalchemy.exc import SQLAlchemyError

from bot.services.server_setup import save_setup
from bot.utils.embeds import meyaya_embed

logger = logging.getLogger(__name__)
FEATURES = {
    "autoresponder": ("Automatic replies", "Occasional replies without a mention; uses the server's chat allowance."),
    "probation": ("3-day newcomer probation", "Block links and attachments from members who joined less than 3 days ago."),
    "cross_spam": ("Cross-channel spam protection", "Remove repeated messages or identical images posted across channels."),
    "anti_invite": ("Other-server invite blocking", "Remove verified invites to other Discord servers."),
}


class ScopeSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="Where should Meyaya chat?", options=[
            discord.SelectOption(label="Entire server", value="server"),
            discord.SelectOption(label="One channel", value="channel"),
        ])

    async def callback(self, interaction):
        view = self.view
        if self.values[0] == "server":
            view.choices["chat_channel_id"] = None
            view.show_features()
        else:
            view.clear_items()
            view.add_item(ChatChannelSelect())
            view.add_cancel()
            view.step = "channel"
        await interaction.response.edit_message(embed=view.embed(), view=view)


class ChatChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="Choose Meyaya's chat channel", channel_types=[
            discord.ChannelType.text, discord.ChannelType.voice, discord.ChannelType.stage_voice,
        ], min_values=1, max_values=1)

    async def callback(self, interaction):
        # show_features clears this dropdown and sets self.view to None.
        # Keep the parent alive locally for the response after that transition.
        view = self.view
        channel = interaction.guild.get_channel(self.values[0].id)
        if channel is None or not view.can_chat(channel, interaction.guild.me):
            await interaction.response.send_message("I need View Channel and Send Messages in that channel.", ephemeral=True)
            return
        view.choices["chat_channel_id"] = channel.id
        view.show_features()
        await interaction.response.edit_message(embed=view.embed(), view=view)


class FeatureSelect(discord.ui.Select):
    def __init__(self, choices):
        super().__init__(placeholder="Choose features to enable (or leave all off)", min_values=0, max_values=4,
            options=[discord.SelectOption(label=label, value=name, description=description[:100], default=choices[name])
                     for name, (label, description) in FEATURES.items()])

    async def callback(self, interaction):
        for name in FEATURES:
            self.view.choices[name] = name in self.values
        for option in self.options:
            option.default = option.value in self.values
        await interaction.response.edit_message(embed=self.view.embed(), view=self.view)


class SetupButton(discord.ui.Button):
    def __init__(self, label, action, style=discord.ButtonStyle.secondary):
        super().__init__(label=label, style=style, row=1)
        self.action = action

    async def callback(self, interaction):
        view = self.view
        if self.action == "cancel":
            view.stop()
            await interaction.response.edit_message(content="Setup cancelled. No settings changed.", embed=None, view=None)
        elif self.action == "review":
            view.clear_items()
            view.step = "review"
            view.add_item(SetupButton("Save settings", "save", discord.ButtonStyle.success))
            view.add_item(SetupButton("Start over", "back"))
            view.add_cancel()
            await interaction.response.edit_message(embed=view.embed(), view=view)
        elif self.action == "back":
            view.show_scope()
            await interaction.response.edit_message(embed=view.embed(), view=view)
        elif self.action == "save":
            await view.save(interaction)


class ServerSetupView(MeyayaView):
    def __init__(self, bot, guild_id, owner_id, choices):
        super().__init__(timeout=300)
        self.bot, self.guild_id, self.owner_id = bot, guild_id, owner_id
        self.choices = dict(choices)
        self.message = None
        self._save_lock = asyncio.Lock()
        self.saved = False
        self.saving = False
        self.show_scope()

    @staticmethod
    def can_chat(channel, member):
        permissions = channel.permissions_for(member)
        return permissions.view_channel and permissions.send_messages

    def add_cancel(self):
        self.add_item(SetupButton("Cancel", "cancel"))

    def show_scope(self):
        self.step = "scope"
        self.clear_items()
        self.add_item(ScopeSelect())
        self.add_cancel()

    def show_features(self):
        self.step = "features"
        self.clear_items()
        self.add_item(FeatureSelect(self.choices))
        self.add_item(SetupButton("Review", "review", discord.ButtonStyle.primary))
        self.add_cancel()

    def embed(self):
        titles = {"scope": "1. Where can Meyaya chat?", "channel": "1. Choose a chat channel", "features": "2. Choose server features", "review": "3. Review your setup"}
        channel = self.choices["chat_channel_id"]
        location = f"<#{channel}> (not its threads)" if channel else "Entire server, where Meyaya has access"
        embed = meyaya_embed("Server Setup", titles[self.step], icon="⚙️")
        embed.add_field(name="Chat access", value=location, inline=False)
        if self.step in {"features", "review"}:
            for name, (label, description) in FEATURES.items():
                embed.add_field(name=f"{'On' if self.choices[name] else 'Off'} - {label}", value=description, inline=False)
        embed.add_field(name="Before you save", value="Changes apply only after Save. Chat access covers mentions, replies, and automatic replies; commands keep their usual access. Moderation needs Manage Messages in the affected channels.", inline=False)
        return embed

    async def interaction_check(self, interaction):
        if self.saving or self.is_finished():
            await interaction.response.send_message("This setup is saving or has already closed.", ephemeral=True)
            return False
        if (interaction.guild_id == self.guild_id and interaction.user.id == self.owner_id
                and interaction.user.guild_permissions.manage_guild):
            return True
        await interaction.response.send_message("Only the server manager who opened this setup can use it.", ephemeral=True)
        return False

    async def save(self, interaction):
        self.saving = True
        await interaction.response.defer()
        async with self._save_lock:
            if self.saved or self.is_finished():
                return
            channel_id = self.choices["chat_channel_id"]
            if channel_id:
                channel = interaction.guild.get_channel(channel_id)
                if channel is None or not self.can_chat(channel, interaction.guild.me):
                    self.saving = False
                    await interaction.followup.send("The selected channel is no longer available to me. Start over and choose another.", ephemeral=True)
                    return
            try:
                await save_setup(self.bot, self.guild_id, self.owner_id, dict(self.choices))
            except SQLAlchemyError:
                self.saving = False
                logger.warning("Server setup could not be saved for guild=%s", self.guild_id)
                await interaction.followup.send("I couldn't save the settings. Nothing was changed; please try again.", ephemeral=True)
                return
            self.saved = True
            self.stop()
            embed = self.embed()
            embed.title = "Server Setup Saved"
            embed.description = "Your settings are now active. Use `serverdashboard` to check usage."
            embed.remove_field(len(embed.fields) - 1)
            await interaction.edit_original_response(embed=embed, view=None)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(content="Setup expired. Run serversetup again; no unsaved changes were applied.", view=self)
            except discord.HTTPException:
                pass
