"""Friendly live stage feedback, pre-flight permission clarity, and Retry UI for heavy commands."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
import logging
from typing import Any

import discord

from bot.utils.components_v2 import MeyayaView, _delivering

logger = logging.getLogger(__name__)


def missing_text_permissions(
    channel: Any,
    me: Any,
    *,
    require_attach: bool = False,
    require_embed: bool = False,
) -> list[str]:
    """Return human-readable missing text channel permissions for Meyaya."""
    if me is None or not hasattr(channel, "permissions_for"):
        return []
    perms = channel.permissions_for(me)
    missing: list[str] = []
    if getattr(perms, "send_messages", True) is False:
        missing.append("Send Messages")
    if require_attach and getattr(perms, "attach_files", True) is False:
        missing.append("Attach Files")
    if require_embed and getattr(perms, "embed_links", True) is False:
        missing.append("Embed Links")
    return missing


def missing_voice_permissions(channel: Any, me: Any) -> list[str]:
    """Return human-readable missing voice/stage permissions for Meyaya."""
    if me is None or not hasattr(channel, "permissions_for"):
        return []
    perms = channel.permissions_for(me)
    missing: list[str] = []
    if getattr(perms, "view_channel", True) is False:
        missing.append("View Channel")
    if getattr(perms, "connect", True) is False:
        missing.append("Connect")
    if isinstance(channel, discord.StageChannel):
        can_speak = getattr(perms, "speak", True) is not False
        can_request = getattr(perms, "request_to_speak", True) is not False
        if not can_speak and not can_request:
            missing.append("Speak / Request to Speak")
    elif getattr(perms, "speak", True) is False:
        missing.append("Speak")
    return missing


def format_missing_permissions(missing: list[str], channel_name: str, purpose: str) -> str:
    """Format an actionable, plain-English missing permission explanation."""
    joined = ", ".join(f"**{perm}**" for perm in missing)
    label = f"**{channel_name}**" if channel_name else "this channel"
    return (
        f"I'm missing {joined} permission in {label} - ask a server admin to enable it "
        f"so I can {purpose}."
    )


class RenderStatus:
    """Single-message live stage progress indicator that cleans itself up after delivery."""

    def __init__(self, ctx: Any, initial_text: str) -> None:
        self.ctx = ctx
        self._initial_text = initial_text
        self._prefix_message: Any = None
        self._used_slash_edit = False
        self._closed = False

    async def __aenter__(self) -> RenderStatus:
        loader = getattr(self.ctx, "_meyaya_loader", None)
        if loader is not None:
            with suppress(Exception):
                await loader.stop()
            self.ctx._meyaya_loader = None
        await self.update(self._initial_text)
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.finish()

    async def update(self, text: str) -> None:
        """Show or edit the single live status line without raising on Discord hiccups."""
        if self._closed or not text:
            return
        interaction = getattr(self.ctx, "interaction", None)
        if interaction is not None:
            edit_orig = getattr(interaction, "edit_original_response", None)
            if callable(edit_orig):
                token = _delivering.set(True)
                try:
                    await asyncio.wait_for(
                        edit_orig(
                            content=text,
                            allowed_mentions=discord.AllowedMentions.none(),
                        ),
                        timeout=4,
                    )
                    self._used_slash_edit = True
                except Exception as exc:
                    logger.debug("Slash render status edit skipped: %s", type(exc).__name__)
                finally:
                    _delivering.reset(token)
            return

        channel = getattr(self.ctx, "channel", None)
        if self._prefix_message is not None:
            token = _delivering.set(True)
            try:
                await asyncio.wait_for(
                    self._prefix_message.edit(
                        content=text,
                        allowed_mentions=discord.AllowedMentions.none(),
                    ),
                    timeout=4,
                )
            except Exception as exc:
                logger.debug("Prefix render status edit skipped: %s", type(exc).__name__)
            finally:
                _delivering.reset(token)
            return

        send_fn = getattr(channel, "send", None)
        if callable(send_fn):
            token = _delivering.set(True)
            try:
                self._prefix_message = await asyncio.wait_for(
                    send_fn(
                        content=text,
                        allowed_mentions=discord.AllowedMentions.none(),
                    ),
                    timeout=4,
                )
            except Exception as exc:
                logger.debug("Prefix render status send skipped: %s", type(exc).__name__)
            finally:
                _delivering.reset(token)

    async def finish(self) -> None:
        """Delete the temporary status message once the real result or error is posted."""
        if self._closed:
            return
        self._closed = True
        msg, self._prefix_message = self._prefix_message, None
        if msg is not None:
            with suppress(Exception):
                await asyncio.wait_for(msg.delete(), timeout=2)
        if self._used_slash_edit:
            self._used_slash_edit = False
            interaction = getattr(self.ctx, "interaction", None)
            delete_orig = getattr(interaction, "delete_original_response", None)
            if callable(delete_orig):
                with suppress(Exception):
                    await asyncio.wait_for(delete_orig(), timeout=2)


class RetryRenderView(MeyayaView):
    """Single-use owner-locked Retry button for transient render or synthesis errors."""

    def __init__(
        self,
        *,
        bot: Any,
        owner_id: int,
        retry_callback: Callable[[discord.Interaction], Awaitable[None]],
        label: str = "Retry",
        timeout: float = 90,
    ) -> None:
        super().__init__(timeout=timeout)
        self._bot = bot
        self._owner_id = owner_id
        self._retry_callback = retry_callback
        self._consumed = False
        button: discord.ui.Button[Any] = discord.ui.Button(
            label=label,
            emoji="🔄",
            style=discord.ButtonStyle.primary,
        )
        button.callback = self._on_retry  # type: ignore[method-assign]
        self._button = button
        self.add_item(button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self._owner_id:
            await interaction.response.send_message(
                "Only the person who ran this command can retry it.",
                ephemeral=True,
            )
            return False
        blacklist = getattr(self._bot, "chat_blacklist", None)
        if blacklist and blacklist.is_command_blocked(interaction.guild_id, interaction.user.id):
            await interaction.response.send_message(
                "Meyaya commands are restricted for you here.",
                ephemeral=True,
            )
            return False
        return True

    async def _on_retry(self, interaction: discord.Interaction) -> None:
        if self._consumed:
            await interaction.response.send_message(
                "Already retrying that request!",
                ephemeral=True,
            )
            return
        self._consumed = True
        self._button.disabled = True
        self.stop()
        with suppress(Exception):
            await interaction.response.edit_message(content="🔄 Retrying...", view=None)
        if not interaction.response.is_done():
            with suppress(Exception):
                await interaction.response.defer(ephemeral=True)
        await self._retry_callback(interaction)


class RetryContextAdapter:
    """Minimal Context-compatible adapter backed by a fresh Retry button interaction."""

    def __init__(
        self,
        bot: Any,
        interaction: discord.Interaction,
        command: Any = None,
    ) -> None:
        self.bot = bot
        self.guild = interaction.guild
        self.channel = interaction.channel
        self.author = interaction.user
        self.command = command
        self.interaction: Any = None
        self._source_interaction = interaction
        self._meyaya_loader: Any = None
        self._meyaya_result_summary = ""

    async def defer(self, *, ephemeral: bool = False) -> None:
        return

    async def send(self, *args: Any, **kwargs: Any) -> Any:
        if args:
            kwargs["content"] = args[0]
        ephemeral = bool(kwargs.pop("ephemeral", False))
        if ephemeral:
            return await self._source_interaction.followup.send(ephemeral=True, **kwargs)
        if self.channel is not None and hasattr(self.channel, "send"):
            return await self.channel.send(**kwargs)
        return await self._source_interaction.followup.send(**kwargs)
