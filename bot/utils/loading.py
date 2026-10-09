"""Per-invocation delayed loading stickers, with best-effort cleanup."""

import asyncio
from contextlib import asynccontextmanager, suppress
from functools import wraps
import logging
import time
from bot.utils.application_emojis import loading_emoji

logger = logging.getLogger(__name__)
LOADING_DELAY = 1.0
STICKER_NAME = "meyaya_loading"
SLOW_COMMANDS = frozenset({
    "profile", "profilecheck", "aura", "palette", "callingcard", "duostyle",
    "fortune", "tarot", "fate", "guardian", "ship", "bestiescore", "rate",
    "rank", "roast", "compliment", "room", "warninglabel", "roleplay",
    "checkclaim", "argumenttimeline", "mostlikely", "reddit", "duck",
})
# Match callbacks that intentionally defer privately. The first defer fixes
# response visibility, so a later callback cannot change a public defer.
PRIVATE_SLASH_COMMANDS = frozenset({"roleplay", "argumenttimeline"})


def resolve_loading_sticker(bot, guild):
    cache = getattr(bot, "_loading_sticker_cache", None)
    if cache is None:
        cache = bot._loading_sticker_cache = {}
    key = getattr(guild, "id", None)
    cached = cache.get(key)
    if cached and time.monotonic() - cached[0] < 60:
        return cached[1]
    sticker = next((item for item in (*getattr(guild, "stickers", ()), *getattr(bot, "stickers", ()))
                    if item.name.casefold() == STICKER_NAME), None)
    if len(cache) >= 128:
        cache.pop(next(iter(cache)))
    cache[key] = (time.monotonic(), sticker)
    if sticker is None:
        logger.debug("loading sticker not found")
    return sticker


class LoadingIndicator:
    def __init__(self, channel, bot, *, delay=LOADING_DELAY, emoji_only=False):
        self.channel, self.bot, self.delay = channel, bot, delay
        self.emoji_only = emoji_only
        self.message = None
        self.task = None
        self.closed = False
        self.sending = False

    def start(self):
        self.task = asyncio.create_task(self._show(), name="meyaya-loading")
        return self

    async def _show(self):
        try:
            await asyncio.sleep(self.delay)
            if self.closed:
                return
            self.sending = True
            emoji = loading_emoji(self.bot)
            if emoji is not None:
                try:
                    self.message = await self.channel.send(str(emoji))
                except Exception as exc:
                    logger.debug("loading emoji could not be sent: %s", type(exc).__name__)
            if self.message is not None or self.emoji_only:
                if self.closed:
                    await self._remove()
                return
            sticker = resolve_loading_sticker(self.bot, getattr(self.channel, "guild", None))
            if sticker is not None:
                try:
                    self.message = await self.channel.send(stickers=[sticker])
                except Exception as exc:
                    logger.debug("loading sticker could not be sent: %s", type(exc).__name__)
            if self.message is None and not self.closed:
                self.message = await self.channel.send("🌸 Meyaya is working on it...")
            if self.closed:
                await self._remove()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("loading indicator failed: %s", type(exc).__name__)

    async def _remove(self):
        message, self.message = self.message, None
        if message is not None:
            try:
                await asyncio.wait_for(message.delete(), timeout=2)
            except Exception as exc:
                logger.debug("loading message cleanup failed: %s", type(exc).__name__)

    async def stop(self):
        self.closed = True
        if self.task is not None and not self.task.done() and not self.sending:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
        # Do not cancel an in-flight POST: it could create an orphan message.
        # _show cleans up its own response if delivery finishes after stop.
        await self._remove()


@asynccontextmanager
async def loading_indicator(channel, bot, *, delay=LOADING_DELAY, emoji_only=False):
    loader = LoadingIndicator(channel, bot, delay=delay, emoji_only=emoji_only).start()
    try:
        yield loader
    finally:
        await loader.stop()


def install_command_loading(bot):
    """Wrap command callbacks only; conversation listeners never get a loader."""
    for command in bot.walk_commands():
        if getattr(command.callback, "_meyaya_loading", False):
            continue
        callback = command.callback

        def wrap(callback, command):
            @wraps(callback)
            async def run(*args, **kwargs):
                ctx = args[1] if command.cog is not None else args[0]
                if getattr(ctx, "_meyaya_loader", None) is not None:
                    return await callback(*args, **kwargs)
                interaction = getattr(ctx, "interaction", None)
                if command.name == "dungeon" and interaction is not None:
                    # Dungeon already defers natively. An extra channel loader
                    # competes with its artwork upload and then needs deletion.
                    return await callback(*args, **kwargs)
                # Preserve existing callbacks' visibility/deferral choices when
                # expanding coverage. Only the original known-safe set pre-defers.
                if command.name in SLOW_COMMANDS and interaction is not None and not interaction.response.is_done():
                    await ctx.defer(ephemeral=command.name in PRIVATE_SLASH_COMMANDS)
                if interaction is not None:
                    # Slash callbacks own their response/defer visibility. Use
                    # Discord's native loading state rather than competing for
                    # channel POST/DELETE rate limits with every invocation.
                    return await callback(*args, **kwargs)
                async with loading_indicator(ctx.channel, bot) as loader:
                    ctx._meyaya_loader = loader
                    try:
                        return await callback(*args, **kwargs)
                    finally:
                        ctx._meyaya_loader = None
            run._meyaya_loading = True
            return run

        command.callback = wrap(callback, command)
        app_command = getattr(command, "app_command", None)
        if app_command is not None:
            # Hybrid slash dispatch owns a reference separate from text dispatch.
            app_command._callback = command.callback

    # Standalone application commands already own their response/defer logic.
