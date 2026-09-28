"""Short member cooldowns and resource limits; chat quotas live in usage.py."""

import asyncio
from contextlib import asynccontextmanager
from functools import wraps
import time
from bot.logging.telemetry import current_model_context, event
from bot.services.llm import GroundingError


class AILimitReached(Exception):
    """A safe, user-facing failure without upstream API details."""


class AIGuard:
    def __init__(self, sessions, settings):
        self.sessions, self.settings = sessions, settings
        self.active = 0
        self.users = {}
        self.voice_guilds = set()
        self.voice_lock = asyncio.Lock()
        self.condition = asyncio.Condition()
        self.waiting = 0
        self.inflight_users = set()

    @asynccontextmanager
    async def request(self):
        if not self.settings.ai_enabled:
            raise AILimitReached("Meyaya's AI features are temporarily paused.")
        now = time.monotonic()
        user_id = current_model_context().get("user_id")
        self.users = {
            user: stamp
            for user, stamp in self.users.items()
            if now - stamp < self.settings.ai_user_cooldown_seconds
        }
        if user_id and (user_id in self.users or user_id in self.inflight_users):
            raise AILimitReached("Please wait a few seconds before another AI request.")
        optional = current_model_context().get('feature') in {'proactive', 'monitor', 'moderation'}
        if user_id:
            self.inflight_users.add(user_id)
        acquired = False
        try:
            async with self.condition:
                if optional and self.waiting:
                    raise AILimitReached("Explicit replies are waiting.")
                if self.active >= self.settings.ai_max_concurrent:
                    capacity = getattr(self.settings, 'ai_queue_size', 0)
                    if optional or self.waiting >= capacity:
                        raise AILimitReached("I'm catching up with a few replies. Please try again shortly.")
                    self.waiting += 1
                    try:
                        async with asyncio.timeout(getattr(self.settings, 'ai_queue_wait_seconds', 6)):
                            await self.condition.wait_for(lambda: self.active < self.settings.ai_max_concurrent)
                    except TimeoutError:
                        raise AILimitReached("I'm still catching up. Please try again in a moment.") from None
                    finally:
                        self.waiting -= 1
                if not self.settings.ai_enabled:
                    raise AILimitReached("Meyaya's AI features are temporarily paused.")
                self.active += 1
                acquired = True
                if user_id:
                    self.users[user_id] = time.monotonic()
            yield
        finally:
            if user_id:
                self.inflight_users.discard(user_id)
            if acquired:
                async with self.condition:
                    self.active -= 1
                    self.condition.notify(1)
            else:
                async with self.condition:
                    self.condition.notify(1)

    async def start_voice(self, guild_id):
        async with self.voice_lock:
            if not self.settings.ai_enabled:
                raise AILimitReached("Meyaya's AI features are temporarily paused.")
            if (
                guild_id in self.voice_guilds
                or len(self.voice_guilds) >= self.settings.voice_max_sessions
            ):
                raise AILimitReached(
                    "All voice slots are busy. Try again when another session ends."
                )
            self.voice_guilds.add(guild_id)

    def end_voice(self, guild_id):
        self.voice_guilds.discard(guild_id)


def guarded(method):
    @wraps(method)
    async def wrapped(self, system_instruction, user_message, *args, **kwargs):
        if self.guard is None:
            return await method(self, system_instruction, user_message, *args, **kwargs)
        try:
            settings = self.guard.settings
            history = kwargs.get("history") or (args[0] if args else None) or []
            size = (
                len(system_instruction)
                + len(user_message)
                + sum(len(item.get("content", "")) for item in history)
            )
            if size > settings.ai_max_input_chars:
                raise AILimitReached("That request is too long. Please shorten it.")
            kwargs["max_output_tokens"] = min(
                kwargs.get("max_output_tokens") or 400, settings.ai_max_output_tokens
            )
            kwargs["timeout_seconds"] = min(kwargs.get("timeout_seconds") or 20, 45)
            async with self.guard.request():
                return await method(self, system_instruction, user_message, *args, **kwargs)
        except AILimitReached as error:
            event("ai_safety_block", reason=str(error))
            if method.__name__ == "grounded_generate":
                raise GroundingError(str(error)) from None
            if current_model_context().get('feature') == 'chat':
                raise
            return None

    return wrapped
