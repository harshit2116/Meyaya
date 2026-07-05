"""Short-term per-channel conversation memory backed by Redis."""

from __future__ import annotations

import json

from redis.asyncio import Redis

HISTORY_TTL_SECONDS = 1800  # conversation resets after 30 minutes of silence
MAX_TURNS = 12  # one turn = one user message + one model reply


class ChatMemoryService:
    """Stores recent conversation turns per Discord channel."""

    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    @staticmethod
    def _key(channel_id: int) -> str:
        return f"chat_history:{channel_id}"

    async def get_history(self, channel_id: int) -> list[dict]:
        """Return Gemini-formatted conversation turns, oldest first."""

        raw = await self.redis.get(self._key(channel_id))
        if not raw:
            return []
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []

    async def append_turn(self, channel_id: int, user_text: str, model_text: str) -> None:
        """Append a completed exchange and trim/expire the history."""

        history = await self.get_history(channel_id)
        history.append({"role": "user", "parts": [{"text": user_text}]})
        history.append({"role": "model", "parts": [{"text": model_text}]})
        history = history[-(MAX_TURNS * 2) :]
        await self.redis.set(self._key(channel_id), json.dumps(history), ex=HISTORY_TTL_SECONDS)