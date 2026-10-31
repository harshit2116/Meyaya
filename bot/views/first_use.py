"""A brief welcome card that can resume the member's original chat request."""

import asyncio

import discord

from bot.utils.components_v2 import MeyayaView
from bot.utils.embeds import meyaya_embed
from bot.views.help import HelpView


def first_use_embed(bot, guild_id, *, can_continue=False):
    enabled = getattr(bot, "feature_enabled", lambda *_: True)
    explore = "**Explore:** `/help` for games and commands."
    if enabled(guild_id, "Fantasy / Profile"):
        explore += " `/awaken` starts your fantasy adventure."
    lines = ["**Chat:** mention me or reply to my messages.", explore]
    if enabled(guild_id, "Memory"):
        lines.append("**Memory:** `/memories` shows what I remember about you.")
    exempt = (
        guild_id == getattr(bot.settings, "quota_exempt_guild_id", None) and guild_id is not None
    )
    allowance = (
        "**Replies:** unlimited in this server."
        if exempt
        else "**Replies:** this server shares a daily chat allowance."
    )
    if guild_id is None:
        allowance = "**Replies:** AI chat works inside servers, using their chat allowance."
    if getattr(bot.settings, "topgg_enabled", False):
        allowance += " `/vote` earns **20 bonus replies for 12 hours**."
    lines.append(allowance)
    ending = (
        "Press **Continue chat** to answer your message."
        if can_continue
        else "Mention me in a server when you're ready to chat."
    )
    return meyaya_embed(
        "Hey, I'm Meyaya!",
        "\n".join(lines) + "\n\n" + ending + " This guide uses no chat replies.",
        icon="🌸",
    )


class FirstUseView(MeyayaView):
    def __init__(self, bot, owner_id, *, chat=None, source=None):
        super().__init__(timeout=180)
        self.bot = bot
        self.owner_id = owner_id
        self.chat = chat
        self.source = source
        self.message = None
        self._continued = False
        if source is not None:
            self.continue_button = discord.ui.Button(
                label="Continue chat", style=discord.ButtonStyle.primary
            )
            self.continue_button.callback = self.continue_chat
            self.add_item(self.continue_button)
        help_button = discord.ui.Button(label="All commands", style=discord.ButtonStyle.secondary)
        help_button.callback = self.open_help
        self.add_item(help_button)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Use /guide to open your own quick guide.", ephemeral=True
            )
            return False
        blacklist = getattr(self.bot, "chat_blacklist", None)
        if blacklist and blacklist.is_command_blocked(interaction.guild_id, interaction.user.id):
            await interaction.response.send_message(
                "Meyaya commands are restricted for you here.", ephemeral=True
            )
            return False
        return True

    async def continue_chat(self, interaction):
        if not await self.interaction_check(interaction):
            return
        if self._continued:
            await interaction.response.send_message(
                "Your chat has already started. Mention me to send another message.", ephemeral=True
            )
            return
        guild_id = self.source.guild.id
        blocked = self.bot.chat_blacklist.is_blocked(guild_id, self.owner_id)
        if (
            blocked
            or not self.bot.feature_enabled(guild_id, "AI Chat")
            or not self.bot.chat_allowed(guild_id, self.source.channel.id)
            or getattr(self.chat, "_closing_chats", False)
        ):
            await interaction.response.send_message(
                "AI chat isn't available here right now. Please mention me again in an enabled chat channel.",
                ephemeral=True,
            )
            return
        self._continued = True
        self.continue_button.disabled = True
        self.continue_button.label = "Chat started"
        await interaction.response.edit_message(view=self)
        try:
            async with asyncio.timeout(5):
                message = await self.source.channel.fetch_message(self.source.id)
        except (discord.HTTPException, TimeoutError, OSError):
            await interaction.followup.send(
                "I couldn't load your original message. Mention me again with your question.",
                ephemeral=True,
            )
            return
        if message.author.id != self.owner_id:
            return
        # Re-enter the normal listener so current moderation, channel access,
        # blacklists, AI availability and quotas all still apply. No direct LLM call.
        await self.chat.on_message(message)

    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        if self.message is not None:
            try:
                async with asyncio.timeout(5):
                    await self.message.edit(view=self)
            except (discord.HTTPException, TimeoutError, OSError):
                pass

    async def open_help(self, interaction):
        prefix = self.bot.prefix_for_guild(interaction.guild_id)
        view = HelpView(
            owner_id=self.owner_id,
            bot_mention=f"<@{self.bot.user.id}>",
            command_prefix=prefix,
            bot=self.bot,
            illustrated=False,
        )
        await interaction.response.send_message(view=view, ephemeral=True)
