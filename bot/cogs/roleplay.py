"""One-shot character roleplay replies sent through cached Discord webhooks."""

from __future__ import annotations

from bot.logging.telemetry import discord_context, event

import logging
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from bot.app import MeyayaBot
from bot.services.usage import ChatLimitReached
from sqlalchemy.exc import SQLAlchemyError
from bot.data.roleplay_personas import ROLEPLAY_PERSONAS, build_roleplay_instruction
from bot.utils.embeds import meyaya_embed

logger = logging.getLogger(__name__)

ROLEPLAY_WEBHOOK_NAME = "Meyaya Roleplay"
MAX_ROLEPLAY_MESSAGE_LENGTH = 1500
RoleplayCharacter = Literal["jungkook", "alya"]


class RoleplayCog(commands.Cog):
    """Generate an isolated character response without changing Meyaya's bot profile."""

    def __init__(self, bot: MeyayaBot) -> None:
        self.bot = bot
        self._webhooks: dict[int, discord.Webhook] = {}

    @commands.hybrid_command(
        name="roleplay",
        aliases=["rp"],
        description="Get a response from an approved roleplay character.",
    )
    @app_commands.describe(
        character="Character who should answer",
        message="What you want to say to the character",
    )
    @commands.cooldown(1, 5.0, commands.BucketType.user)
    @discord_context("roleplay")
    async def roleplay(
        self,
        ctx: commands.Context,
        character: RoleplayCharacter,
        *,
        message: str,
    ) -> None:
        """Generate one response and deliver it using the selected RP identity."""

        message = message.strip()
        if not message or len(message) > MAX_ROLEPLAY_MESSAGE_LENGTH:
            await ctx.send(
                embed=meyaya_embed(
                    "Roleplay Message",
                    f"Please give me a message between 1 and {MAX_ROLEPLAY_MESSAGE_LENGTH} characters.",
                    tone="warning",
                    icon="🎭",
                ),
                ephemeral=ctx.interaction is not None,
            )
            return

        webhook_channel, thread = self._webhook_destination(ctx.channel)
        if webhook_channel is None or ctx.guild is None:
            await self._send_error(ctx, "Roleplay is available only in server text channels.")
            return

        bot_member = ctx.guild.me
        if bot_member is None or not webhook_channel.permissions_for(bot_member).manage_webhooks:
            await self._send_error(
                ctx,
                "I need the Manage Webhooks permission in this channel for character identities.",
            )
            return

        llm = self.bot.build_llm_provider()
        if llm is None:
            await self._send_error(ctx, "My roleplay brain is unavailable right now.")
            return

        if ctx.interaction is not None:
            await ctx.defer(ephemeral=True)

        persona = ROLEPLAY_PERSONAS[character]
        speaker = f"{ctx.author.display_name} (Discord user ID {ctx.author.id})"
        instruction = build_roleplay_instruction(character, speaker)

        try:
            async with ctx.typing():
                generated = await self.bot.generate_chat(
                    ctx.guild.id,
                    instruction,
                    message,
                    max_output_tokens=300,
                )
            if generated is None or not generated.text.strip():
                await self._send_error(ctx, f"{persona.display_name} could not answer right now.")
                return

            await self._send_as_persona(
                webhook_channel,
                thread,
                character,
                ctx.author,
                generated.text.strip(),
            )
            if ctx.interaction is not None:
                await ctx.interaction.edit_original_response(
                    content=f"{persona.display_name} replied."
                )
        except ChatLimitReached as exc:
            await self._send_error(ctx, str(exc))
        except SQLAlchemyError:
            await self._send_error(
                ctx, "I can't check this server's allowance right now. Please try again shortly."
            )
        except (discord.Forbidden, discord.HTTPException):
            logger.exception(
                "Roleplay delivery failed channel=%s character=%s",
                webhook_channel.id,
                character,
            )
            await self._send_error(
                ctx,
                "Discord would not let me send that roleplay response. Check my webhook permissions.",
            )

    async def _send_as_persona(
        self,
        channel: discord.TextChannel | discord.ForumChannel,
        thread: discord.Thread | None,
        character: str,
        author: discord.Member | discord.User,
        response: str,
    ) -> None:
        """Send through a cached bot-owned webhook, recreating it if it was deleted."""

        persona = ROLEPLAY_PERSONAS[character]
        avatar_url = self._avatar_url(character)
        available = 2000 - len(author.mention) - 1
        content = f"{author.mention} {response[:available].rstrip()}"
        kwargs: dict[str, object] = {
            "username": persona.display_name,
            "allowed_mentions": discord.AllowedMentions.none(),
            "wait": True,
        }
        if avatar_url:
            kwargs["avatar_url"] = avatar_url
        if thread is not None:
            kwargs["thread"] = thread

        webhook = await self._get_webhook(channel)
        try:
            await webhook.send(content, **kwargs)
        except discord.NotFound:
            self._webhooks.pop(channel.id, None)
            webhook = await self._get_webhook(channel)
            await webhook.send(content, **kwargs)

    async def _get_webhook(
        self,
        channel: discord.TextChannel | discord.ForumChannel,
    ) -> discord.Webhook:
        cached = self._webhooks.get(channel.id)
        if cached is not None:
            return cached

        bot_id = self.bot.user.id if self.bot.user is not None else None
        for webhook in await channel.webhooks():
            owner_id = webhook.user.id if webhook.user is not None else None
            if webhook.name == ROLEPLAY_WEBHOOK_NAME and owner_id == bot_id and webhook.token:
                self._webhooks[channel.id] = webhook
                return webhook

        webhook = await channel.create_webhook(
            name=ROLEPLAY_WEBHOOK_NAME,
            reason="Meyaya character roleplay replies",
        )
        self._webhooks[channel.id] = webhook
        return webhook

    def _avatar_url(self, character: str) -> str:
        if character == "jungkook":
            configured = self.bot.settings.jungkook_roleplay_avatar_url
        else:
            configured = self.bot.settings.alya_roleplay_avatar_url
        if configured.strip():
            return configured.strip()
        if self.bot.user is not None:
            return self.bot.user.display_avatar.url
        return ""

    @staticmethod
    def _webhook_destination(
        channel: discord.abc.Messageable | None,
    ) -> tuple[discord.TextChannel | discord.ForumChannel | None, discord.Thread | None]:
        if isinstance(channel, discord.Thread):
            parent = channel.parent
            if isinstance(parent, (discord.TextChannel, discord.ForumChannel)):
                return parent, channel
            return None, None
        if isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
            return channel, None
        return None, None

    @staticmethod
    async def _send_error(ctx: commands.Context, description: str) -> None:
        embed = meyaya_embed(
            "Roleplay Unavailable",
            description,
            tone="danger",
            icon="🎭",
        )
        if ctx.interaction is not None and ctx.interaction.response.is_done():
            await ctx.interaction.edit_original_response(content=None, embed=embed)
        else:
            await ctx.send(embed=embed, ephemeral=ctx.interaction is not None)


async def setup(bot: MeyayaBot) -> None:
    """Install the roleplay command."""

    await bot.add_cog(RoleplayCog(bot))
