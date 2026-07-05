"""Google Gemini chat completion logic."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import aiohttp

logger = logging.getLogger(__name__)

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
REQUEST_TIMEOUT_SECONDS = 20
MAX_OUTPUT_TOKENS = 400
MAX_REPLY_WORDS = 220  # safety net only, keeps us well under Discord's 2000 char limit

REMEMBER_PATTERN = re.compile(r"<remember>(.*?)</remember>", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class GeminiReply:
    text: str
    memories: list[str]


class GeminiService:
    """Thin wrapper around the Gemini REST API."""

    def __init__(self, api_key: str, model: str, http_session: aiohttp.ClientSession) -> None:
        self.api_key = api_key
        self.model = model
        self.http_session = http_session

    async def generate(
        self,
        system_instruction: str,
        user_message: str,
        history: list[dict] | None = None,
    ) -> GeminiReply | None:
        """Ask Gemini for a reply, optionally continuing a prior conversation."""

        if not self.api_key:
            logger.warning("Gemini API key is not configured; skipping generation.")
            return None

        url = GEMINI_ENDPOINT.format(model=self.model)
        contents = list(history or [])
        contents.append({"role": "user", "parts": [{"text": user_message}]})

        payload = {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": contents,
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
                    return GeminiReply(
                        text="*yawns* ...I'm all out of energy for now, ask me again in a bit! 😴",
                        memories=[],
                    )
                if response.status != 200:
                    body = await response.text()
                    logger.error("Gemini request failed (%s): %s", response.status, body)
                    return None
                data = await response.json()
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.error("Gemini request errored: %s", exc)
            return None

        raw_text = self._extract_text(data)
        if not raw_text:
            return None

        visible_text, memories = self._split_memories(raw_text)
        visible_text = self._limit_words(visible_text, MAX_REPLY_WORDS)
        if not visible_text:
            return None
        return GeminiReply(text=visible_text, memories=memories)

    @staticmethod
    def _extract_text(payload: dict) -> str | None:
        try:
            candidates = payload["candidates"]
            parts = candidates[0]["content"]["parts"]
            visible_parts = [part for part in parts if not part.get("thought", False)]
            text = "".join(part.get("text", "") for part in visible_parts).strip()
            return text or None
        except (KeyError, IndexError, TypeError):
            logger.error("Unexpected Gemini response shape: %s", payload)
            return None

    @staticmethod
    def _split_memories(text: str) -> tuple[str, list[str]]:
        memories = [match.strip() for match in REMEMBER_PATTERN.findall(text) if match.strip()]
        visible_text = REMEMBER_PATTERN.sub("", text).strip()
        return visible_text, memories

    @staticmethod
    def _limit_words(text: str, max_words: int) -> str:
        words = text.split()
        if len(words) <= max_words:
            return text
        return " ".join(words[:max_words]).rstrip(".,!?") + "..."