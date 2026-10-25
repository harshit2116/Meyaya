"""Conservative text rules and a shared, persistent server-local access gate."""

import re
import unicodedata
import time
from collections import OrderedDict
from bot.services.chat_boundaries import direct_hostility, model_hostility_eligible
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from bot.models.chat_blacklist import ChatBlacklist


def explicit_request(text: str) -> bool:
    """Match direct sexual solicitations, not mentions of sex or general profanity.

    Deliberately incomplete: no claim of semantic moderation or image detection.
    Quoted lines and educational/reporting language are excluded to reduce mistakes.
    """
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r'```[\s\S]*?```|`[^`]*`|"[^"]*"', "", text)
    text = " ".join(line for line in text.splitlines() if not line.lstrip().startswith(">"))
    if re.search(
        r"\b(?:report|reported|reporting|quoted|someone said|someone asked|he said|she said|what does|meaning of|consent|education|medical|health|don't|do not|stop)\b",
        text,
    ):
        return False
    return any(
        re.search(pattern, text)
        for pattern in (
            r"\b(?:send|show|give)\s+(?:me\s+)?(?:your\s+)?(?:nudes|nude pics|naked pics)\b",
            r"\b(?:write|generate|create|describe)\s+(?:me\s+)?(?:an?\s+)?(?:explicit\s+)?(?:porn|pornographic|erotic sex)\b",
            r"\b(?:have sex with me|fuck me|suck my dick|suck my cock)\b",
            r"\b(?:let'?s|can we|please)\s+(?:sext|do erotic roleplay)\b",
        )
    )


async def acknowledge_silently(ctx):
    """Avoid Discord's interaction-failed banner without sending a response."""
    if ctx.interaction is not None:
        if not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(ephemeral=True)
        await ctx.interaction.delete_original_response()


class ChatBlacklistService:
    def __init__(self, sessions):
        self.sessions = sessions
        self.blocked = frozenset()
        self.ready = False
        self.ai_only = frozenset()
        self._rudeness = OrderedDict()
        self._pending_rudeness = set()

    async def load(self):
        async with self.sessions() as session:
            rows = (
                await session.execute(
                    select(ChatBlacklist.guild_id, ChatBlacklist.user_id, ChatBlacklist.source).where(
                        ChatBlacklist.active.is_(True)
                    )
                )
            ).all()
        self.blocked = frozenset((row[0], row[1]) for row in rows)
        self.ai_only = frozenset((row[0], row[1]) for row in rows if len(row) > 2 and row[2] == 'ai_rudeness')
        self.ready = True

    def is_blocked(self, guild_id, user_id):
        return guild_id is not None and (not self.ready or (guild_id, user_id) in self.blocked or (guild_id, user_id) in self._pending_rudeness)

    def is_command_blocked(self, guild_id, user_id):
        key = (guild_id, user_id)
        return self.is_blocked(guild_id, user_id) and key not in self.ai_only and key not in self._pending_rudeness

    async def note_rudeness(self, guild_id, user_id, text, *, message_id, directed=False, signal=None):
        if self.is_blocked(guild_id, user_id):
            return True
        hostile = direct_hostility(text, directed=directed)
        # A model signal extends language coverage, but only for a directly
        # addressed new message. Quotes and requests to interpret text do not count.
        if not hostile and signal == 'rude':
            hostile = model_hostility_eligible(text, directed=directed)
        if not hostile:
            return False
        now = time.monotonic()
        key = (guild_id, user_id)
        entries = [(stamp, mid) for stamp, mid in self._rudeness.get(key, ()) if now - stamp < 1800]
        if any(mid == message_id for _, mid in entries):
            return len(entries) >= 3
        entries.append((now, message_id))
        self._rudeness[key] = entries[-3:]
        self._rudeness.move_to_end(key)
        while len(self._rudeness) > 2048:
            self._rudeness.popitem(last=False)
        if len(entries) < 3:
            return False
        self._pending_rudeness.add(key)
        try:
            await self.set(guild_id, user_id, active=True, source='ai_rudeness',
                           reason='Repeated direct hostility toward Meyaya: 3 distinct messages within 30 minutes. AI chat only.')
        finally:
            self._pending_rudeness.discard(key)
        return True

    async def set(self, guild_id, user_id, *, active, reason, source="manual", actor_id=None):
        async with self.sessions() as session:
            values = dict(
                guild_id=guild_id,
                user_id=user_id,
                active=active,
                reason=reason[:300],
                source=source,
                actor_id=actor_id,
            )
            statement = insert(ChatBlacklist).values(**values)
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=[ChatBlacklist.guild_id, ChatBlacklist.user_id],
                    set_={**values, "updated_at": func.now()},
                )
            )
            await session.commit()
        key = (guild_id, user_id)
        self.blocked = self.blocked | {key} if active else self.blocked - {key}
        self.ai_only = self.ai_only | {key} if active and source == 'ai_rudeness' else self.ai_only - {key}
        if not active:
            self._rudeness.pop(key, None)

    async def inspect(self, guild_id, user_id, text):
        if self.is_blocked(guild_id, user_id):
            return True
        if guild_id is not None and explicit_request(text):
            await self.set(
                guild_id,
                user_id,
                active=True,
                reason="Explicit sexual solicitation directed at Meyaya (automatic text rule)",
                source="automatic",
            )
            return True
        return False
