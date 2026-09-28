"""Google Gemini chat completion logic."""

from __future__ import annotations

import asyncio
import logging
import json
import re
import time
from dataclasses import dataclass

import aiohttp

from bot.logging.telemetry import observe, record_response, request_failure

from bot.services.llm import (
    ChatMessage,
    LLMProvider,
    GroundedCitation,
    GroundedReply,
    GroundingError,
    GroundingRateLimitError,
    MemoryAction,
    MemoryDirective,
    NaturalCommand,
    LLMReply as GeminiReply,
)

logger = logging.getLogger(__name__)

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_INTERACTIONS_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"
REQUEST_TIMEOUT_SECONDS = 20
MAX_OUTPUT_TOKENS = 400
MAX_REPLY_WORDS = 220  # safety net only, keeps us well under Discord's 2000 char limit
RETRYABLE_STATUS_CODES = {502, 503, 504}
MAX_REQUEST_ATTEMPTS = 2
PROVIDER_COOLDOWN_SECONDS = 30


@dataclass
class GeminiAvailability:
    failures: int = 0
    retry_at: float = 0
    probing: bool = False


class GeminiService(LLMProvider):
    """Thin wrapper around the Gemini REST API."""

    provider_name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        http_session: aiohttp.ClientSession,
        *,
        thinking_budget: int | None = 0,
        thinking_level: str | None = None,
        availability: GeminiAvailability | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.http_session = http_session
        self.thinking_budget = thinking_budget
        self.thinking_level = thinking_level
        self.default_timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
        self.availability = availability if availability is not None else GeminiAvailability()

    def _transient_failure(self):
        state = self.availability
        state.failures += 1
        if state.failures >= 2:
            state.retry_at = time.monotonic() + PROVIDER_COOLDOWN_SECONDS

    async def _error_details(self, response):
        # Never log arbitrary provider text: it can echo prompts or credentials.
        # Only emit known status values and locally classified message categories.
        try:
            async with asyncio.timeout(1):
                raw = bytearray()
                while len(raw) <= 4096:
                    chunk = await response.content.read(4097 - len(raw))
                    if not chunk:
                        break
                    raw.extend(chunk)
            if len(raw) > 4096:
                return {"error_category": "oversized_error"}
            data = json.loads(raw)
            error = data.get("error", {}) if isinstance(data, dict) else {}
            if not isinstance(error, dict):
                return {}
            status = error.get("status")
            statuses = {"UNAVAILABLE", "RESOURCE_EXHAUSTED", "INVALID_ARGUMENT",
                        "PERMISSION_DENIED", "UNAUTHENTICATED", "NOT_FOUND", "INTERNAL",
                        "FAILED_PRECONDITION", "DEADLINE_EXCEEDED"}
            message = str(error.get("message", "")).casefold()
            category = "unspecified"
            for phrase, label in (("policy checks", "policy_checks_unavailable"),
                                  ("high demand", "high_demand"),
                                  ("overload", "overloaded"),
                                  ("quota", "quota"),
                                  ("api key", "api_key"),
                                  ("not found", "not_found")):
                if phrase in message:
                    category = label
                    break
            return {"provider_status": status if isinstance(status, str) and status in statuses else "UNKNOWN",
                    "error_category": category}
        except (ValueError, aiohttp.ClientError, TimeoutError):
            return {}

    @observe("generate_text")
    async def generate_text(
        self,
        system_instruction: str,
        user_message: str,
        history: list[ChatMessage] | None = None,
        *,
        max_output_tokens: int | None = None,
        timeout_seconds: int | None = None,
    ) -> str | None:
        state = self.availability
        if state.retry_at > time.monotonic() or state.probing:
            request_failure("provider_cooldown")
            return None
        probe = bool(state.retry_at)
        if probe:
            state.probing = True
        try:
            result = await self._generate_text(
                system_instruction, user_message, history,
                max_output_tokens=max_output_tokens, timeout_seconds=timeout_seconds)
            if result and result.strip():
                state.failures = 0
                state.retry_at = 0
            elif probe:
                # A failed recovery probe must not unleash concurrent retries.
                state.retry_at = time.monotonic() + PROVIDER_COOLDOWN_SECONDS
            return result
        except asyncio.CancelledError:
            if probe:
                state.retry_at = time.monotonic() + PROVIDER_COOLDOWN_SECONDS
            raise
        finally:
            if probe:
                state.probing = False

    async def _generate_text(
        self, system_instruction, user_message, history=None, *,
        max_output_tokens=None, timeout_seconds=None,
    ) -> str | None:
        """Ask Gemini for a reply, optionally continuing a prior conversation."""

        if not self.api_key:
            request_failure("missing_api_key")
            logger.warning("Gemini API key is not configured; skipping generation.")
            return None

        url = GEMINI_ENDPOINT.format(model=self.model)
        contents = [
            {
                "role": "model" if item["role"] == "assistant" else "user",
                "parts": [{"text": item["content"]}],
            }
            for item in history or []
        ]
        contents.append({"role": "user", "parts": [{"text": user_message}]})

        generation_config: dict[str, object] = {
            "maxOutputTokens": max_output_tokens or MAX_OUTPUT_TOKENS,
        }
        if self.thinking_level is not None:
            generation_config["thinkingConfig"] = {"thinkingLevel": self.thinking_level}
        elif self.thinking_budget is not None:
            generation_config["thinkingConfig"] = {"thinkingBudget": self.thinking_budget}
        payload = {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": contents,
            "generationConfig": generation_config,
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
                    if response.status >= 400:
                        request_failure(f"http_{response.status}", attempt=attempt,
                                        **await self._error_details(response))
                    if response.status == 429:
                        logger.warning("Gemini rate limit hit.")
                        return None
                    if response.status in RETRYABLE_STATUS_CODES and attempt < MAX_REQUEST_ATTEMPTS:
                        logger.warning(
                            "Gemini temporarily unavailable status=%s; retrying attempt=%s",
                            response.status,
                            attempt + 1,
                        )
                        await asyncio.sleep(0.5 * attempt)
                        continue
                    if response.status != 200:
                        if response.status in RETRYABLE_STATUS_CODES:
                            self._transient_failure()
                        logger.error(
                            "Gemini request failed status=%s",
                            response.status,
                        )
                        return None
                    response_data = await response.json()
                    if not isinstance(response_data, dict):
                        logger.error("Gemini returned a non-object JSON response")
                        return None
                    record_response(response_data)
                    data = response_data
                    break
            except (aiohttp.ClientError, TimeoutError) as exc:
                request_failure(type(exc).__name__, attempt=attempt)
                if isinstance(exc, TimeoutError):
                    # Let the router try a different model rather than spending
                    # another full timeout on the same unavailable endpoint.
                    self._transient_failure()
                    return None
                if attempt < MAX_REQUEST_ATTEMPTS:
                    logger.warning(
                        "Gemini request errored; retrying attempt=%s error=%s",
                        attempt + 1,
                        type(exc).__name__,
                    )
                    await asyncio.sleep(0.5 * attempt)
                    continue
                logger.error("Gemini request failed after retry: %s", type(exc).__name__)
                self._transient_failure()
                return None

        if data is None:
            return None

        raw_text = self._extract_text(data)
        resp_id = data.get("responseId") if isinstance(data, dict) else None
        model_version = data.get("modelVersion") if isinstance(data, dict) else None
        logger.debug("Gemini responseId=%s modelVersion=%s", resp_id, model_version)
        if not raw_text:
            return None

        return raw_text

    @observe("grounded_generate")
    async def grounded_generate(
        self,
        system_instruction: str,
        user_message: str,
        *,
        max_output_tokens: int = 1800,
        timeout_seconds: int = 45,
    ) -> GroundedReply:
        """Generate source-annotated text, with a compatible endpoint fallback."""

        if not self.api_key:
            request_failure("missing_api_key")
            raise GroundingError("Gemini API key is not configured")

        interactions_payload = {
            "model": self.model.removeprefix("models/"),
            "system_instruction": system_instruction,
            "input": user_message,
            "tools": [{"type": "google_search"}],
            "store": False,
            "generation_config": {"max_output_tokens": max_output_tokens},
        }
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        rate_limit_retry: int | None = None
        was_rate_limited = False

        data, status, retry_after = await self._post_grounded_request(
            GEMINI_INTERACTIONS_ENDPOINT,
            interactions_payload,
            headers,
            timeout,
            endpoint_name="Interactions",
        )
        if status == 200 and data is not None:
            result = self._extract_grounded_reply(data)
            if result is not None:
                return result
            logger.warning("Gemini Interactions grounding returned no usable model text.")
        if status == 429:
            was_rate_limited = True
            rate_limit_retry = retry_after

        request_failure("grounding_endpoint_fallback", endpoint="Interactions")

        # The Interactions API is newer and its availability can differ by model,
        # project, or quota. GenerateContent supports the same Google Search tool.
        generation_config: dict[str, object] = {
            "maxOutputTokens": max_output_tokens,
        }
        if self.thinking_level is not None:
            generation_config["thinkingConfig"] = {"thinkingLevel": self.thinking_level}
        elif self.thinking_budget is not None:
            generation_config["thinkingConfig"] = {"thinkingBudget": self.thinking_budget}
        generate_payload = {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"role": "user", "parts": [{"text": user_message}]}],
            "tools": [{"google_search": {}}],
            "generationConfig": generation_config,
        }
        generate_url = GEMINI_ENDPOINT.format(model=self.model.removeprefix("models/"))
        data, status, retry_after = await self._post_grounded_request(
            generate_url,
            generate_payload,
            headers,
            timeout,
            endpoint_name="GenerateContent",
        )
        if status == 200 and data is not None:
            result = self._extract_generate_content_grounded_reply(data)
            if result is not None:
                return result
            logger.warning("Gemini GenerateContent grounding returned no usable model text.")
        if status == 429:
            was_rate_limited = True
            rate_limit_retry = retry_after or rate_limit_retry

        if was_rate_limited:
            raise GroundingRateLimitError(rate_limit_retry)
        raise GroundingError("Both grounded Gemini endpoints failed")

    async def _post_grounded_request(
        self,
        url: str,
        payload: dict,
        headers: dict[str, str],
        timeout: aiohttp.ClientTimeout,
        *,
        endpoint_name: str,
    ) -> tuple[dict | None, int | None, int | None]:
        """Post one grounded request and retain safe quota diagnostics."""

        for attempt in range(1, MAX_REQUEST_ATTEMPTS + 1):
            try:
                async with self.http_session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=timeout,
                ) as response:
                    retry_after = self._retry_after_seconds(response.headers.get("Retry-After"))
                    if response.status >= 400:
                        request_failure(f"http_{response.status}", attempt=attempt)
                    if response.status == 429:
                        body = await response.text()
                        logger.warning(
                            "Gemini %s grounding rate limit hit retry_after=%s detail=%s",
                            endpoint_name,
                            retry_after,
                            "provider_error",
                        )
                        return None, response.status, retry_after
                    if response.status in RETRYABLE_STATUS_CODES and attempt < MAX_REQUEST_ATTEMPTS:
                        await asyncio.sleep(0.5 * attempt)
                        continue
                    if response.status != 200:
                        body = await response.text()
                        logger.error(
                            "Gemini %s grounded request failed status=%s detail=%s",
                            endpoint_name,
                            response.status,
                            "provider_error",
                        )
                        return None, response.status, retry_after
                    data = await response.json()
                    if not isinstance(data, dict):
                        return None, response.status, retry_after
                    record_response(data)
                    return data, response.status, retry_after
            except (aiohttp.ClientError, TimeoutError) as exc:
                request_failure(type(exc).__name__, attempt=attempt)
                if attempt < MAX_REQUEST_ATTEMPTS:
                    logger.warning(
                        "Gemini %s grounded request errored; retrying attempt=%s error=%s",
                        endpoint_name,
                        attempt + 1,
                        exc,
                    )
                    await asyncio.sleep(0.5 * attempt)
                    continue
                logger.error(
                    "Gemini %s grounded request failed after retry: %s",
                    endpoint_name,
                    type(exc).__name__,
                )
                return None, None, None
        return None, None, None

    @staticmethod
    def _retry_after_seconds(raw_value: str | None) -> int | None:
        if raw_value is None:
            return None
        try:
            return max(1, int(float(raw_value)))
        except ValueError:
            return None

    @staticmethod
    def _safe_google_error(raw_body: str) -> str:
        """Keep logs actionable without dumping an entire remote response."""

        compact = " ".join(raw_body.split())
        return compact[:500] or "no response body"

    @staticmethod
    def _extract_grounded_reply(payload: dict) -> GroundedReply | None:
        """Read current and legacy Interactions API text annotation shapes."""

        output_blocks: list[dict] = []
        steps = payload.get("steps")
        if isinstance(steps, list):
            for step in steps:
                if not isinstance(step, dict) or step.get("type") != "model_output":
                    continue
                content = step.get("content")
                if isinstance(content, list):
                    output_blocks = [block for block in content if isinstance(block, dict)]

        if not output_blocks:
            outputs = payload.get("outputs")
            if isinstance(outputs, list):
                output_blocks = [block for block in outputs if isinstance(block, dict)]

        text_parts: list[str] = []
        citations: list[GroundedCitation] = []
        offset = 0
        for block in output_blocks:
            if block.get("type") != "text" or not isinstance(block.get("text"), str):
                continue
            text = block["text"]
            annotations = block.get("annotations")
            if isinstance(annotations, list):
                for annotation in annotations:
                    if not isinstance(annotation, dict):
                        continue
                    if annotation.get("type") != "url_citation":
                        continue
                    url = annotation.get("url")
                    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
                        continue
                    title = annotation.get("title")
                    start = annotation.get("start_index", 0)
                    end = annotation.get("end_index", len(text))
                    if not isinstance(start, int) or not isinstance(end, int):
                        continue
                    citations.append(
                        GroundedCitation(
                            title=str(title or "Source")[:120],
                            url=url,
                            start_index=offset + max(0, start),
                            end_index=offset + min(len(text), max(start, end)),
                        )
                    )
            text_parts.append(text)
            offset += len(text)

        combined = "".join(text_parts).strip()
        if not combined:
            return None
        return GroundedReply(text=combined, citations=tuple(citations))

    @classmethod
    def _extract_generate_content_grounded_reply(cls, payload: dict) -> GroundedReply | None:
        """Read text and Google Search citations from GenerateContent."""

        text = cls._extract_text(payload)
        candidates = payload.get("candidates")
        if not text or not isinstance(candidates, list) or not candidates:
            return None
        candidate = candidates[0]
        if not isinstance(candidate, dict):
            return None
        metadata = candidate.get("groundingMetadata") or candidate.get("grounding_metadata")
        if not isinstance(metadata, dict):
            return GroundedReply(text=text, citations=())

        chunks = metadata.get("groundingChunks") or metadata.get("grounding_chunks") or []
        supports = metadata.get("groundingSupports") or metadata.get("grounding_supports") or []
        citations: list[GroundedCitation] = []
        if isinstance(chunks, list) and isinstance(supports, list):
            for support in supports:
                if not isinstance(support, dict):
                    continue
                segment = support.get("segment")
                if not isinstance(segment, dict):
                    segment = {}
                start = segment.get("startIndex", segment.get("start_index", 0))
                end = segment.get("endIndex", segment.get("end_index", len(text)))
                indices = support.get(
                    "groundingChunkIndices", support.get("grounding_chunk_indices", [])
                )
                if not isinstance(start, int) or not isinstance(end, int):
                    continue
                if not isinstance(indices, list):
                    continue
                for index in indices:
                    if not isinstance(index, int) or not 0 <= index < len(chunks):
                        continue
                    chunk = chunks[index]
                    if not isinstance(chunk, dict):
                        continue
                    web = chunk.get("web")
                    if not isinstance(web, dict):
                        continue
                    url = web.get("uri")
                    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
                        continue
                    citations.append(
                        GroundedCitation(
                            title=str(web.get("title") or "Source")[:120],
                            url=url,
                            start_index=max(0, min(len(text), start)),
                            end_index=max(0, min(len(text), max(start, end))),
                        )
                    )

        if not citations and isinstance(chunks, list):
            for chunk in chunks:
                web = chunk.get("web") if isinstance(chunk, dict) else None
                url = web.get("uri") if isinstance(web, dict) else None
                if isinstance(url, str) and url.startswith(("https://", "http://")):
                    citations.append(
                        GroundedCitation(
                            title=str(web.get("title") or "Source")[:120],
                            url=url,
                            start_index=len(text),
                            end_index=len(text),
                        )
                    )
        return GroundedReply(text=text, citations=tuple(citations))

    @staticmethod
    def _extract_text(payload: dict) -> str | None:
        try:
            candidates = payload["candidates"]
            parts = candidates[0]["content"]["parts"]
            visible_parts = [part for part in parts if not part.get("thought", False)]
            text = "".join(part.get("text", "") for part in visible_parts).strip()
            return text or None
        except (KeyError, IndexError, TypeError):
            logger.error("Unexpected Gemini response shape")
            return None
