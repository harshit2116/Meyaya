"""Separate command work from Discord response delivery in slow-command logs."""

import logging
import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from bot.utils.command_timing import add_stage
from discord.ext import commands
from bot.utils.components_v2 import v2_payload

logger = logging.getLogger(__name__)
_MAX_COMMAND_OUTPUTS = 512
_COMMAND_OUTPUT_TTL = 24 * 60 * 60
MAX_RESULT_SUMMARY = 2000


@dataclass(frozen=True, slots=True)
class CommandOutput:
    command: str
    invoker_id: int
    invoker_name: str
    result_summary: str = ""


def remember_command_result(ctx, **result) -> None:
    """Attach bounded result data to the next public response, never to user memory."""
    summary = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    ctx._meyaya_result_summary = (
        summary if len(summary) <= MAX_RESULT_SUMMARY
        else summary[:MAX_RESULT_SUMMARY - 3] + "..."
    )


def command_output_for(bot, channel_id: int, message_id: int) -> CommandOutput | None:
    outputs = getattr(bot, "_meyaya_command_outputs", None)
    if outputs is None:
        return None
    entry = outputs.get((channel_id, message_id))
    if entry is None:
        return None
    created_at, output = entry
    if time.monotonic() - created_at > _COMMAND_OUTPUT_TTL:
        outputs.pop((channel_id, message_id), None)
        return None
    return output


class TimedContext(commands.Context):
    async def defer(self, *, ephemeral=False):
        if self.interaction is not None and self.interaction.response.is_done():
            return
        return await super().defer(ephemeral=ephemeral)

    async def send(self, *args, **kwargs):
        if args:
            kwargs["content"] = args[0]
            args = args[1:]
        kwargs = v2_payload(kwargs, force=True)
        loader = getattr(self, "_meyaya_loader", None)
        started = time.monotonic()
        try:
            loading_message = getattr(loader, "message", None)
            if (getattr(kwargs.get("view"), "command_name", None) == "dungeon"
                    and loading_message is not None and not getattr(loading_message, "stickers", ())
                    and set(kwargs) <= {"view", "allowed_mentions", "file", "files"}):
                # Upgrade the already-visible loader into the dungeon card.
                # This avoids a second channel POST and a later DELETE, while
                # retaining the real returned message for view tracking.
                edit = dict(kwargs, content=None, embeds=[])
                uploads = edit.pop("files", [])
                image = edit.pop("file", None)
                if image is not None:
                    uploads = [image]
                edit["attachments"] = uploads
                sent = await loading_message.edit(**edit)
                loader.message = None
            else:
                sent = await super().send(*args, **kwargs)
            command = getattr(self, "command", None)
            if (command is not None and sent is not None
                    and not kwargs.get("ephemeral", False)
                    and getattr(sent, "id", None) is not None):
                invoker = self.interaction.user if self.interaction is not None else self.author
                outputs = getattr(self.bot, "_meyaya_command_outputs", None)
                if outputs is None:
                    outputs = OrderedDict()
                    self.bot._meyaya_command_outputs = outputs
                outputs[(self.channel.id, sent.id)] = (
                    time.monotonic(),
                    CommandOutput(
                        command=command.qualified_name,
                        invoker_id=invoker.id,
                        invoker_name=invoker.display_name[:80],
                        result_summary=getattr(self, "_meyaya_result_summary", ""),
                    ),
                )
                while len(outputs) > _MAX_COMMAND_OUTPUTS:
                    outputs.popitem(last=False)
            return sent
        finally:
            # Do not accidentally attach one card's data to a later response.
            self._meyaya_result_summary = ""
            elapsed = (time.monotonic() - started) * 1000
            add_stage('delivery_ms', elapsed)
            if elapsed >= 500:
                # API call duration includes library retries and pre/post-response
                # rate-limit waits; it is not message-visible latency.
                logger.info("discord_delivery command=%s api_call_ms=%.0f includes_rate_limit_waits=true",
                            getattr(getattr(self, "command", None), "qualified_name", "unknown"), elapsed)
            # Keep the loading message through the attachment upload. Removing
            # it first leaves a blank gap while Discord is still receiving the GIF.
            # Also clean up after failed/cancelled sends; wrappers remain idempotent.
            if loader is not None:
                cleanup_started = time.monotonic()
                try:
                    await loader.stop()
                finally:
                    cleanup_ms = (time.monotonic() - cleanup_started) * 1000
                    add_stage('loading_cleanup_ms', cleanup_ms)
                    if cleanup_ms >= 500:
                        logger.info("discord_loading_cleanup command=%s cleanup_ms=%.0f",
                                    getattr(getattr(self, "command", None), "qualified_name", "unknown"), cleanup_ms)
