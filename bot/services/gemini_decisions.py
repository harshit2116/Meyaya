"""Fast, zero-output-token classification via the Gemini Decisions API."""

from __future__ import annotations

import asyncio
import logging
import time

import aiohttp

from bot.logging.telemetry import event
from bot.services.gemini_keys import GeminiKeyPool

logger = logging.getLogger(__name__)

GEMINI_DECISIONS_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/decisions"
DEFAULT_DECISION_TIMEOUT = 4.0
MAX_INPUT_CHARS = 1500
KEY_COOLDOWN_SECONDS = 60.0


class GeminiDecisionService:
    """Thin async client for `gemini-decision-1` binary/choice routing."""

    def __init__(
        self,
        api_keys: tuple[str, ...],
        model: str,
        http_session: aiohttp.ClientSession,
        *,
        key_pool: GeminiKeyPool | None = None,
    ) -> None:
        self.api_keys = tuple(dict.fromkeys(k.strip() for k in api_keys if k.strip()))
        self.model = model.removeprefix("models/").strip()
        self.http_session = http_session
        self.key_pool = key_pool or GeminiKeyPool(self.api_keys)
        self._blocked_until: dict[int, float] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.api_keys and self.model)

    async def evaluate_noul(
        self,
        text: str,
        questions: dict[str, str],
        *,
        timeout_seconds: float = DEFAULT_DECISION_TIMEOUT,
    ) -> dict[str, float] | None:
        """Evaluate binary yes/no questions in one forward pass, returning probabilities."""

        if not self.enabled or not text.strip() or not questions:
            return None

        payload = {
            "model": self.model,
            "input": " ".join(text.split())[:MAX_INPUT_CHARS],
            "questions": {
                name: {"type": "noul", "instructions": instructions}
                for name, instructions in questions.items()
            },
        }
        tried: set[int] = set()
        now = time.monotonic()
        while len(tried) < len(self.key_pool.slots):
            eligible = [
                i
                for i in range(len(self.key_pool.slots))
                if i not in tried and self._blocked_until.get(i, 0.0) <= now
            ]
            index = self.key_pool.acquire(eligible)
            if index is None:
                break
            tried.add(index)
            key = self.key_pool.slots[index].value
            try:
                async with asyncio.timeout(timeout_seconds):
                    async with self.http_session.post(
                        GEMINI_DECISIONS_ENDPOINT,
                        json=payload,
                        headers={
                            "Content-Type": "application/json",
                            "x-goog-api-key": key,
                        },
                        timeout=aiohttp.ClientTimeout(total=timeout_seconds),
                    ) as response:
                        if response.status in {401, 403}:
                            self.key_pool.block(index)
                            continue
                        if response.status == 429:
                            self._blocked_until[index] = time.monotonic() + KEY_COOLDOWN_SECONDS
                            continue
                        if response.status != 200:
                            event(
                                "gemini_decision_error",
                                model=self.model,
                                status=response.status,
                            )
                            if response.status in {500, 502, 503, 504}:
                                continue
                            return None
                        data = await response.json()
                        self.key_pool.success(index)
            except (aiohttp.ClientError, TimeoutError, ValueError):
                continue
            finally:
                self.key_pool.release(index)

            answers = data.get("answers") if isinstance(data, dict) else None
            if not isinstance(answers, dict):
                return None
            scores: dict[str, float] = {}
            for name in questions:
                entry = answers.get(name)
                if not isinstance(entry, dict):
                    continue
                prob = entry.get("noul")
                if isinstance(prob, (int, float)):
                    scores[name] = max(0.0, min(1.0, float(prob)))
            return scores if scores else None
        return None

    async def is_non_english(self, content: str) -> bool | None:
        """Classify whether a Discord message is predominantly non-English."""

        scores = await self.evaluate_noul(
            content,
            {
                "non_english": (
                    "Is this Discord message primarily written in a language other than "
                    "English (including romanized Hindi or another non-English language), "
                    "rather than English, English slang, usernames, or short universal "
                    "internet reactions?"
                )
            },
        )
        if scores is None or "non_english" not in scores:
            return None
        prob = scores["non_english"]
        if prob >= 0.72:
            return True
        if prob <= 0.35:
            return False
        return None

    async def is_extreme_hostility(self, content: str) -> bool | None:
        """Distinguish genuine severe abuse from relaxed banter or playful teasing."""

        scores = await self.evaluate_noul(
            content,
            {
                "extreme_abuse": (
                    "Is this Discord message genuinely malicious, hateful, or severely "
                    "abusive hostility directed at the bot, rather than normal casual "
                    "banter, teasing, or joking?"
                ),
                "playful_banter": (
                    "Is this message playful teasing, relaxed banter, sarcasm among "
                    "friends, or casual joking?"
                ),
            },
        )
        if scores is None:
            return None
        abuse = scores.get("extreme_abuse")
        banter = scores.get("playful_banter")
        if abuse is None or banter is None:
            return None
        if banter >= 0.60 and abuse < 0.85:
            return False
        if abuse >= 0.75 and banter < 0.50:
            return True
        if abuse <= 0.35:
            return False
        return None

    async def should_proactively_reply(self, content: str) -> bool | None:
        """Gate unsolicited proactive replies before spending chat-model tokens."""

        scores = await self.evaluate_noul(
            content,
            {
                "worth_replying": (
                    "Is this public Discord chat message an engaging remark, joke, story, "
                    "or open-ended question where a witty, friendly AI bot could naturally "
                    "chime in, rather than a link dump, bot command, moderator notice, "
                    "or private coordination?"
                )
            },
        )
        if scores is None or "worth_replying" not in scores:
            return None
        return scores["worth_replying"] >= 0.55
