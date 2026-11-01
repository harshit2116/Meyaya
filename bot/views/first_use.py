"""A brief welcome card that can resume the member's original chat request."""

import asyncio
import logging
import time

import discord
from discord.ext import commands
from discord.ext.commands.view import StringView
from sqlalchemy.exc import SQLAlchemyError

from bot.utils.components_v2 import MeyayaView
from bot.utils.embeds import meyaya_embed
from bot.utils.image_work import ImageBusy
from bot.views.help import HelpView

logger = logging.getLogger(__name__)


def first_use_embed(bot, guild_id, *, can_continue=False, page=0, command_name=None):
    enabled = getattr(bot, "feature_enabled", lambda *_: True)
    if page == 1:
        lines = []
        if enabled(guild_id, "Voice Chat"):
            lines.append(
                "**🎙️ Join VC and talk with me**\n"
                "Join a voice channel, use `/join`, and we can talk together. `/leave` ends the session."
            )
        if enabled(guild_id, "Fantasy / Profile"):
            lines.append(
                "**⚔️ Your adventure starts here**\n"
                "Use `/awaken` to discover your fantasy character, then `/dungeon` to start exploring."
            )
        if enabled(guild_id, "Multiplayer Games"):
            lines.append(
                "**🎲 Bring your friends**\n"
                "Try `/showdown`, `/survive`, or `/excuse` for playful challenges, choices, and a little chaos."
            )
        if not lines:
            lines.append(
                "Some activities are disabled in this server. `/help` shows the command directory."
            )
        if command_name:
            lines.append(f"You're ready! **Continue command** resumes `/{command_name}`.")
        else:
            lines.append(
                "You're ready! **Start chatting** answers your original message."
                if can_continue
                else "You're ready! Press **Send Meyaya hello** to start a conversation in this channel."
            )
        embed = meyaya_embed("Let's do something together!", "\n\n".join(lines), icon="🌸")
        embed.set_footer(text="2 / 2 · End of guide · Reopen anytime with /guide")
        return embed

    lines = [
        "Your companion for conversations, adventures, and a little fun with friends.",
        (
            "**What can Meyaya do?**\n"
            "💬 **Chat with you:** mention me or reply to my messages.\n"
            "✨ **Check your style:** review your avatar, banner, and overall profile look.\n"
            "🎮 **Play together:** discover voice chat, adventures, and multiplayer games on the next screen."
        ),
    ]
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
    lines.append(allowance + " The guide uses no chat replies.")
    embed = meyaya_embed(
        "Hello, I am Meyaya!",
        "\n\n".join(lines),
        icon="🌸",
    )
    embed.set_footer(text="1 / 2 · Take a look at your profile, continue, or skip the guide")
    return embed


class FirstUseView(MeyayaView):
    def __init__(
        self, bot, owner_id, *, chat=None, source=None, guild_id=None, command_context=None
    ):
        super().__init__(timeout=180)
        self.bot = bot
        self.owner_id = owner_id
        self.chat = chat
        self.source = source
        self.command_context = command_context
        self.command_name = (
            command_context.command.qualified_name if command_context is not None else None
        )
        self.message = None
        self._continued = False
        self._finished_guide = False
        self._guide_page = 0
        self._state_lock = asyncio.Lock()
        self._profile_busy = False
        self._last_profile = float("-inf")
        self.guild_id = source.guild.id if source is not None else guild_id
        self.continue_button = discord.ui.Button(
            label=(
                "Continue command"
                if command_context is not None
                else "Start chatting" if source is not None else "Send Meyaya hello"
            ),
            style=discord.ButtonStyle.primary,
        )
        self.continue_button.callback = self.continue_chat
        self._build_controls()

    def _button(self, label, callback, *, primary=False):
        button = discord.ui.Button(
            label=label,
            style=discord.ButtonStyle.primary if primary else discord.ButtonStyle.secondary,
        )
        button.callback = callback
        self.add_item(button)

    def _build_controls(self):
        self.clear_items()
        if self._finished_guide:
            if self._continued:
                self.continue_button.disabled = True
                self.continue_button.label = (
                    "Command resumed" if self.command_context is not None else "Chat started"
                )
                self.add_item(self.continue_button)
            self._button("All commands", self.open_help)
        elif self._guide_page == 0:
            self._button("Next", self.next_page, primary=True)
            self._button("Profile check", self.open_profile)
            self._button("Skip guide", self.skip_guide)
        else:
            self.add_item(self.continue_button)
            self._button("Back", self.previous_page)
            self._button("All commands", self.open_help)

    async def _show_page(self, interaction, page):
        if not await self.interaction_check(interaction):
            return
        async with self._state_lock:
            if self._finished_guide:
                await interaction.response.send_message(
                    "Your guide is finished. Use /guide to reopen it.", ephemeral=True
                )
                return
            self._guide_page = page
            self.guild_id = interaction.guild_id
            self._build_controls()
            await interaction.response.edit_message(
                embed=first_use_embed(
                    self.bot,
                    self.guild_id,
                    can_continue=self.source is not None,
                    page=page,
                    command_name=self.command_name,
                ),
                view=self,
            )

    async def next_page(self, interaction):
        await self._show_page(interaction, 1)

    async def previous_page(self, interaction):
        await self._show_page(interaction, 0)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Use /guide to open your own quick guide.", ephemeral=True
            )
            return False
        if self.is_finished():
            await interaction.response.send_message(
                "This guide has expired. Use /guide to reopen it.", ephemeral=True
            )
            return False
        blacklist = getattr(self.bot, "chat_blacklist", None)
        if blacklist and blacklist.is_command_blocked(interaction.guild_id, interaction.user.id):
            await interaction.response.send_message(
                "Meyaya commands are restricted for you here.", ephemeral=True
            )
            return False
        return True

    def _chat_target(self, interaction):
        guild_id = self.source.guild.id if self.source is not None else interaction.guild_id
        channel = self.source.channel if self.source is not None else interaction.channel
        chat = self.chat or self.bot.get_cog("ChatCog")
        blocked = self.bot.chat_blacklist.is_blocked(guild_id, self.owner_id)
        if (
            guild_id is None
            or channel is None
            or chat is None
            or blocked
            or not self.bot.feature_enabled(guild_id, "AI Chat")
            or not self.bot.chat_allowed(guild_id, channel.id)
            or getattr(chat, "_closing_chats", False)
        ):
            return None
        return chat

    async def continue_chat(self, interaction):
        if not await self.interaction_check(interaction):
            return
        chat = self._chat_target(interaction) if self.command_context is None else None
        if self.command_context is None and chat is None:
            await interaction.response.send_message(
                "AI chat isn't available here right now. Please mention me again in an enabled chat channel.",
                ephemeral=True,
            )
            return
        async with self._state_lock:
            if self._finished_guide:
                await interaction.response.send_message(
                    "Your guide has finished. Mention me to send another message.", ephemeral=True
                )
                return
            self._continued = True
            self._finished_guide = True
            self._build_controls()
            await interaction.response.edit_message(
                embed=meyaya_embed(
                    (
                        "Continuing your command!"
                        if self.command_context is not None
                        else "You're ready to chat!"
                    ),
                    (
                        f"Resuming `/{self.command_name}`."
                        if self.command_context is not None
                        else "Mention me or reply to my messages anytime. `/help` is here when you need it."
                    ),
                    icon="🌸",
                ),
                view=self,
            )
        service = getattr(self.bot, "first_use", None)
        if service is not None:
            service.remember(self.owner_id)
        if self.command_context is not None:
            await self._resume_command(interaction)
            return
        if self.source is None:
            await chat.on_message(GuideInputMessage(self.bot, interaction), immediate=True)
            return
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
        context = await self.bot.get_context(message)
        if context.valid:
            await self.bot.invoke(context)
        else:
            await chat.on_message(message, immediate=True)

    async def _resume_command(self, interaction):
        original = self.command_context
        if self.bot.get_command(self.command_name) is not original.command:
            await interaction.followup.send(
                "That command has changed. Please run it again.", ephemeral=True
            )
            return
        try:
            async with asyncio.timeout(5):
                member = await original.guild.fetch_member(self.owner_id)
                if original.interaction is None:
                    message = await original.channel.fetch_message(original.message.id)
                    if message.author.id != self.owner_id:
                        return
                    message.author = member
                    moderation = self.bot.get_cog("ModerationCog")
                    if moderation is not None and await moderation.should_block(message):
                        return
                    context = await self.bot.get_context(message)
                    if not context.valid or context.command is not original.command:
                        await interaction.followup.send(
                            "Your original command was changed. Please run it again.",
                            ephemeral=True,
                        )
                        return
                else:
                    if original.interaction.is_expired():
                        await interaction.followup.send(
                            "Your original command has expired. Please run it again.",
                            ephemeral=True,
                        )
                        return
                    context = original
                    context.author = member
                    context.message.author = member
                    context.interaction.user = member
                    permissions_for = getattr(context.channel, "permissions_for", None)
                    if not callable(permissions_for) or context.guild.me is None:
                        await interaction.followup.send(
                            "I couldn't refresh channel access. Please run your command again.",
                            ephemeral=True,
                        )
                        return
                    # Slash permission checks otherwise read the old interaction
                    # snapshot, which can be stale after the member reads a guide.
                    context.interaction._permissions = permissions_for(member).value
                    context.interaction._app_permissions = permissions_for(context.guild.me).value
                    context.args = (
                        [context.command.cog, context]
                        if context.command.cog is not None
                        else [context]
                    )
                    context.interaction._baton = context
        except (discord.HTTPException, TimeoutError, OSError):
            await interaction.followup.send(
                "I couldn't reload your original command or member access. Please run the command again.",
                ephemeral=True,
            )
            return
        context.command_failed = False
        if context.interaction is not None:
            context.interaction.command_failed = False
        blacklist = getattr(self.bot, "chat_blacklist", None)
        if blacklist is not None and blacklist.is_command_blocked(context.guild.id, self.owner_id):
            await interaction.followup.send(
                "Meyaya commands are restricted for you here.", ephemeral=True
            )
            return
        # Full invocation rechecks permissions, feature switches, cooldowns and
        # concurrency before executing. No callback-only shortcut or AI fallback.
        try:
            await self.bot.invoke(context)
        except discord.app_commands.AppCommandError as error:
            context.command_failed = True
            context.interaction.command_failed = True
            await self.bot.on_app_command_error(context.interaction, error)
        if context.interaction is not None and not context.command_failed:
            self.bot.dispatch(
                "app_command_completion", context.interaction, context.command.app_command
            )

    async def skip_guide(self, interaction):
        if not await self.interaction_check(interaction):
            return
        if self.command_context is not None or self._chat_target(interaction) is not None:
            await self.continue_chat(interaction)
            return
        async with self._state_lock:
            if self._finished_guide:
                await interaction.response.send_message(
                    "Your guide is already finished. Use /guide to reopen it.", ephemeral=True
                )
                return
            self._finished_guide = True
            self._build_controls()
            await interaction.response.edit_message(
                embed=meyaya_embed(
                    "See you around!",
                    "Mention me when you're ready to talk. You can reopen this guide with `/guide`.",
                    icon="🌸",
                ),
                view=self,
            )

    async def open_profile(self, interaction):
        if not await self.interaction_check(interaction):
            return
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "Open /guide inside a server to check your profile.", ephemeral=True
            )
            return
        if self._finished_guide or self._profile_busy or time.monotonic() - self._last_profile < 10:
            await interaction.response.send_message(
                "Give your profile a moment before opening it again.", ephemeral=True
            )
            return
        command = self.bot.get_command("profilecheck")
        if command is None:
            await interaction.response.send_message(
                "Profile check is unavailable right now. Try /profilecheck shortly.", ephemeral=True
            )
            return
        self._profile_busy = True
        self._last_profile = time.monotonic()
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
            async with asyncio.timeout(30):
                await self.bot.invoke(GuideProfileContext(self.bot, interaction, command))
        except (
            commands.CommandError,
            SQLAlchemyError,
            discord.HTTPException,
            TimeoutError,
            OSError,
            ImageBusy,
        ) as error:
            logger.warning("Onboarding profile unavailable error=%s", type(error).__name__)
            await interaction.followup.send(
                "I couldn't check your profile just now. You can keep going or try /profilecheck later.",
                ephemeral=True,
            )
        finally:
            self._profile_busy = False

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
        if not await self.interaction_check(interaction):
            return
        prefix = self.bot.prefix_for_guild(interaction.guild_id)
        view = HelpView(
            owner_id=self.owner_id,
            bot_mention=f"<@{self.bot.user.id}>",
            command_prefix=prefix,
            bot=self.bot,
            illustrated=False,
        )
        await interaction.response.send_message(view=view, ephemeral=True)


class GuideInputMessage:
    """Explicit button input through the existing chat and command paths."""

    def __init__(self, bot, interaction, *, content=None):
        self._origin = interaction.message
        self._state = interaction._state
        self.id = interaction.id
        # An interaction ID identifies the event, not a fetchable Discord post.
        self._meyaya_source_message_id = None
        self.author = interaction.user
        self.guild = interaction.guild
        self.channel = interaction.channel
        self.content = content or f"<@{bot.user.id}> Hello Meyaya!"
        self.mentions = [bot.user]
        self.role_mentions = []
        self.channel_mentions = []
        self.attachments = []
        self.stickers = []
        self.reference = None
        self.mention_everyone = False
        self.edited_at = None
        self.created_at = interaction.created_at

    def __getattr__(self, name):
        origin = self.__dict__.get("_origin")
        if origin is None:
            raise AttributeError(name)
        return getattr(origin, name)

    async def reply(self, content=None, **kwargs):
        kwargs.pop("mention_author", None)
        kwargs["allowed_mentions"] = discord.AllowedMentions.none()
        # Application follow-ups become V2 command cards in the shared transport.
        # A greeting is ordinary chat, so use the normal channel delivery path.
        return await self.channel.send(content=content, **kwargs)


class GuideProfileContext(commands.Context):
    """Invoke /profilecheck with its real checks and cooldown, privately."""

    def __init__(self, bot, interaction, command):
        super().__init__(
            message=GuideInputMessage(bot, interaction, content="/profilecheck"),
            bot=bot,
            view=StringView(""),
            prefix="/",
            command=command,
            invoked_with="profilecheck",
            interaction=interaction,
        )
        # Hybrid parsing supplies keyword arguments from the interaction's empty
        # namespace; prefix invocation still needs the bound callback arguments.
        self.args = [command.cog, self] if command.cog is not None else [self]
        interaction._baton = self

    async def defer(self, *, ephemeral=True):
        if not self.interaction.response.is_done():
            await self.interaction.response.defer(ephemeral=True, thinking=True)

    async def send(self, *args, **kwargs):
        kwargs["ephemeral"] = True
        return await super().send(*args, **kwargs)
