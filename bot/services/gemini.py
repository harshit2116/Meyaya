"""Google Gemini chat completion logic."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import aiohttp

logger = logging.getLogger(__name__)

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
REQUEST_TIMEOUT_SECONDS = 20
MAX_OUTPUT_TOKENS = 400
MAX_REPLY_WORDS = 30


@dataclass(frozen=True)
class GeminiReply:
    text: str


class GeminiService:
    """Thin wrapper around the Gemini REST API."""

    def __init__(self, api_key: str, model: str, http_session: aiohttp.ClientSession) -> None:
        self.api_key = api_key
        self.model = model
        self.http_session = http_session

    async def generate(self, system_instruction: str, user_message: str) -> GeminiReply | None:
        """Ask Gemini for a reply. Returns None if the API key is missing or the call fails."""

        if not self.api_key:
            logger.warning("Gemini API key is not configured; skipping generation.")
            return None

        url = GEMINI_ENDPOINT.format(model=self.model)
        payload = {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"role": "user", "parts": [{"text": user_message}]}],
            "generationConfig": {
                "maxOutputTokens": MAX_OUTPUT_TOKENS,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        headers = {"Content-Type": "application/json"}
        params = {"key": self.api_key}

        try:
            async with self.http_session.post(
                url,
                json=payload,
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
            ) as response:
                if response.status == 429:
                    logger.warning("Gemini rate limit hit.")
                    return GeminiReply(text="*yawns* ...I'm all out of energy for now, ask me again in a bit! 😴")
                if response.status != 200:
                    body = await response.text()
                    logger.error("Gemini request failed (%s): %s", response.status, body)
                    return None
                
                data = await response.json()
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.error("Gemini request errored: %s", exc)
            return None

        text = self._extract_text(data)
        if not text:
            return None
        return GeminiReply(text=text)

    @staticmethod
    def _extract_text(payload: dict) -> str | None:
        try:
            candidates = payload["candidates"]
            parts = candidates[0]["content"]["parts"]
            visible_parts = [part for part in parts if not part.get("thought", False)]
            text = "".join(part.get("text", "") for part in visible_parts).strip()
        except (KeyError, IndexError, TypeError):
            logger.error("Unexpected Gemini response shape: %s", payload)
            return None

        if not text:
            return None

        return GeminiService._limit_words(text, MAX_REPLY_WORDS)

    @staticmethod
    def _limit_words(text: str, max_words: int) -> str:
        words = text.split()
        if len(words) <= max_words:
            return text
        return " ".join(words[:max_words]).rstrip(".,!?") + "..."