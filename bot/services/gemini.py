"""Google Gemini chat completion logic."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

import aiohttp

logger = logging.getLogger(__name__)

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
REQUEST_TIMEOUT_SECONDS = 20
MAX_OUTPUT_TOKENS = 400
MAX_REPLY_WORDS = 220  # safety net only, keeps us well under Discord's 2000 char limit
RETRYABLE_STATUS_CODES = {502, 503, 504}
MAX_REQUEST_ATTEMPTS = 2

REMEMBER_PATTERN = re.compile(r"<remember>(.*?)</remember>", re.IGNORECASE | re.DOTALL)
LORE_PATTERN = re.compile(r"<lore>(.*?)</lore>", re.IGNORECASE | re.DOTALL)
ACTION_PATTERN = re.compile(r"<action>(.*?)</action>", re.IGNORECASE | re.DOTALL)
COMMAND_PATTERN = re.compile(r"<command>(.*?)</command>", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True, slots=True)
class NaturalCommand:
    """One validated-shaped command request parsed from Gemini output."""

    name: str
    target_id: int | None


@dataclass(frozen=True)
class GeminiReply:
    text: str
    memories: list[str]
    lore: list[str]
    actions: list[str]
    commands: list[NaturalCommand]


class GeminiService:
    """Thin wrapper around the Gemini REST API."""

    def __init__(self, api_key: str, model: str, http_session: aiohttp.ClientSession) -> None:
        self.api_key = api_key
        self.model = model
        self.http_session = http_session
        self.default_timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)

    async def generate(
        self,
        system_instruction: str,
        user_message: str,
        history: list[dict] | None = None,
        *,
        max_output_tokens: int | None = None,
        timeout_seconds: int | None = None,
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
                "maxOutputTokens": max_output_tokens or MAX_OUTPUT_TOKENS,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        headers = {"Content-Type": "application/json"}
        params = {"key": self.api_key}

        timeout = (
            aiohttp.ClientTimeout(total=timeout_seconds)
            if timeout_seconds is not None
            else self.default_timeout
        )
        data: dict | None = None
        for attempt in range(1, MAX_REQUEST_ATTEMPTS + 1):
            try:
                async with self.http_session.post(
                    url,
                    json=payload,
                    headers=headers,
                    params=params,
                    timeout=timeout,
                ) as response:
                    logger.debug(
                        "Gemini request sent model=%s status=%s payload_keys=%s",
                        self.model,
                        response.status,
                        list(payload.keys()),
                    )
                    if response.status == 429:
                        logger.warning("Gemini rate limit hit.")
                        return GeminiReply(
                            text="*yawns* ...I'm all out of energy for now, ask me again in a bit! 😴",
                            memories=[],
                            lore=[],
                            actions=[],
                            commands=[],
                        )
                    if response.status in RETRYABLE_STATUS_CODES and attempt < MAX_REQUEST_ATTEMPTS:
                        logger.warning(
                            "Gemini temporarily unavailable status=%s; retrying attempt=%s",
                            response.status,
                            attempt + 1,
                        )
                        await asyncio.sleep(0.5 * attempt)
                        continue
                    if response.status != 200:
                        body = await response.text()
                        logger.error(
                            "Gemini request failed status=%s body=%s",
                            response.status,
                            body[:1000],
                        )
                        return None
                    response_data = await response.json()
                    if not isinstance(response_data, dict):
                        logger.error("Gemini returned a non-object JSON response")
                        return None
                    data = response_data
                    break
            except (aiohttp.ClientError, TimeoutError) as exc:
                if attempt < MAX_REQUEST_ATTEMPTS:
                    logger.warning(
                        "Gemini request errored; retrying attempt=%s error=%s",
                        attempt + 1,
                        exc,
                    )
                    await asyncio.sleep(0.5 * attempt)
                    continue
                logger.error("Gemini request failed after retry: %s", exc)
                return None

        if data is None:
            return None

        raw_text = self._extract_text(data)
        resp_id = data.get("responseId") if isinstance(data, dict) else None
        model_version = data.get("modelVersion") if isinstance(data, dict) else None
        logger.debug("Gemini responseId=%s modelVersion=%s", resp_id, model_version)
        if not raw_text:
            return None

        visible_text, memories, lore, actions, commands = self._split_directives(raw_text)
        logger.debug(
            "Gemini extracted_text_len=%d snippet=%s",
            len(visible_text),
            (visible_text[:300] + "...") if len(visible_text) > 300 else visible_text,
        )
        visible_text = self._limit_words(visible_text, MAX_REPLY_WORDS)
        if not visible_text:
            return None
        return GeminiReply(
            text=visible_text,
            memories=memories,
            lore=lore,
            actions=actions,
            commands=commands,
        )

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
    def _split_directives(
        text: str,
    ) -> tuple[str, list[str], list[str], list[str], list[NaturalCommand]]:
        memories = [match.strip() for match in REMEMBER_PATTERN.findall(text) if match.strip()]
        lore = [match.strip() for match in LORE_PATTERN.findall(text) if match.strip()]
        actions = [match.strip().casefold() for match in ACTION_PATTERN.findall(text) if match.strip()]
        commands = []
        for raw_command in COMMAND_PATTERN.findall(text):
            name, separator, raw_target_id = raw_command.strip().partition(":")
            if separator and name.strip() and raw_target_id.strip().isdigit():
                commands.append(
                    NaturalCommand(
                        name=name.strip().casefold(),
                        target_id=int(raw_target_id.strip()),
                    )
                )
            elif not separator and name.strip():
                commands.append(
                    NaturalCommand(name=name.strip().casefold(), target_id=None)
                )
        visible_text = REMEMBER_PATTERN.sub("", text)
        visible_text = LORE_PATTERN.sub("", visible_text)
        visible_text = ACTION_PATTERN.sub("", visible_text).strip()
        visible_text = COMMAND_PATTERN.sub("", visible_text).strip()
        return visible_text, memories[:1], lore[:1], actions[:1], commands[:1]

    @staticmethod
    def _limit_words(text: str, max_words: int) -> str:
        words = text.split()
        if len(words) <= max_words:
            return text
        return " ".join(words[:max_words]).rstrip(".,!?") + "..."
