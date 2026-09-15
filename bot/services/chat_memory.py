"""Short-term per-channel conversation memory backed by Redis."""

from __future__ import annotations

import json
import logging
import time

from redis.asyncio import Redis
from redis.exceptions import RedisError

from bot.services.llm import ChatMessage

logger = logging.getLogger(__name__)

HISTORY_TTL_SECONDS = 1800  # conversation resets after 30 minutes of silence
MAX_TURNS = 12  # one turn = one user message + one model reply


class ChatMemoryService:
    """Stores recent conversation turns per Discord channel."""

    def __init__(self, redis: Redis) -> None:
        self.redis = redis
        self._last_warning = float("-inf")

    def _warn_unavailable(self) -> None:
        now = time.monotonic()
        if now - self._last_warning >= 60:
            logger.warning("Redis unavailable; short-term chat history is temporarily unavailable")
            self._last_warning = now

    @staticmethod
    def _key(channel_id: int, user_id: int) -> str:
        # Direct conversations are isolated by both channel and member. This
        # prevents one person's Meyaya conversation from leaking into another's.
        # v5 stores each message as one Redis list item. This makes appends
        # atomic and avoids a read/modify/write race between overlapping turns.
        return f"chat_history:v5:{channel_id}:{user_id}"

    async def get_history(self, channel_id: int, user_id: int) -> list[ChatMessage]:
        """Return neutral turns, including older Gemini-shaped Redis entries."""

        try:
            raw_items = await self.redis.lrange(
                self._key(channel_id, user_id), 0, MAX_TURNS * 2 - 1
            )
        except RedisError:
            self._warn_unavailable()
            return []

        history: list[ChatMessage] = []
        for raw in raw_items:
            try:
                item = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            if role not in {"user", "assistant", "model"}:
                continue
            content = item.get("content")
            if not isinstance(content, str):
                parts = item.get("parts")
                if not isinstance(parts, list):
                    continue
                content = "".join(
                    part["text"]
                    for part in parts
                    if isinstance(part, dict) and isinstance(part.get("text"), str)
                )
            if content:
                history.append(
                    {
                        "role": "user" if role == "user" else "assistant",
                        "content": content,
                    }
                )
        return history

    async def append_turn(
        self,
        channel_id: int,
        user_id: int,
        user_text: str,
        model_text: str,
        *,
        speaker_label: str | None = None,
    ) -> None:
        """Append a completed exchange and trim/expire the history. No-ops on Redis failure."""

        history_text = f"[{speaker_label}] {user_text}" if speaker_label else user_text
        entries = (
            {"role": "user", "content": history_text},
            {"role": "assistant", "content": model_text},
        )
        key = self._key(channel_id, user_id)

        try:
            async with self.redis.pipeline(transaction=False) as pipe:
                pipe.rpush(key, *(json.dumps(entry) for entry in entries))
                pipe.ltrim(key, -(MAX_TURNS * 2), -1)
                pipe.expire(key, HISTORY_TTL_SECONDS)
                await pipe.execute()
        except RedisError:
            self._warn_unavailable()
