"""Feature-aware model selection behind the provider-neutral interface."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum
import asyncio
from typing import Any, cast

from bot.logging.telemetry import current_model_context, event, record_route_deadline
from bot.services.llm import (
    ChatMessage,
    GroundedReply,
    GroundingError,
    GroundingRateLimitError,
    LLMProvider,
)
from bot.services.ai_guard import guarded, AILimitReached


class ModelTier(StrEnum):
    FAST = "fast"
    BALANCED = "balanced"
    REASONING = "reasoning"
    GROUNDED = "grounded"


LIGHT_FEATURES = frozenset(
    {
        "fun",
        "roast",
        "compliment",
        "excuse",
    }
)
FAST_FEATURES = frozenset(
    {
        "monitor",
        "moderation",
        "proactive",
        "reddit",
        "fun",
        "roast",
        "compliment",
        "rank",
        "voice_summary",
    }
)
REASONING_FEATURES = frozenset(
    {
        "argument_timeline",
        "court",
        "social_games",
        "showdown",
        "excuse",
        "survive",
    }
)


class ModelRouter(LLMProvider):
    provider_name = "router"
    model = "feature-routed"
    _supports_response_mime_type = True

    def __init__(
        self,
        providers: dict[ModelTier, LLMProvider],
        *,
        guard: Any = None,
        fallback: LLMProvider | None = None,
        tier_fallbacks: Mapping[ModelTier, Sequence[LLMProvider]] | None = None,
        light_providers: Sequence[LLMProvider] | None = None,
    ) -> None:
        required = {ModelTier.FAST, ModelTier.BALANCED, ModelTier.REASONING, ModelTier.GROUNDED}
        missing = required.difference(providers)
        if missing:
            raise ValueError(f"Missing model tiers: {sorted(tier.value for tier in missing)}")
        self.providers = providers
        self.guard = guard
        self.fallback = fallback
        self.tier_fallbacks: dict[ModelTier, tuple[LLMProvider, ...]] = {
            tier: tuple(items) for tier, items in (tier_fallbacks or {}).items()
        }
        self.light_providers: tuple[LLMProvider, ...] = tuple(light_providers or ())
        self.key_pool: Any = None

    @staticmethod
    def _provider_identity(provider: LLMProvider) -> tuple[Any, Any]:
        return (getattr(provider, "provider_name", None), getattr(provider, "model", None))

    def _dedupe_candidates(self, candidates: Sequence[LLMProvider]) -> list[LLMProvider]:
        seen: set[tuple[Any, Any]] = set()
        ordered: list[LLMProvider] = []
        for candidate in candidates:
            identity = self._provider_identity(candidate)
            if identity in seen:
                continue
            seen.add(identity)
            ordered.append(candidate)
        return ordered

    async def _safe_text(
        self,
        provider: LLMProvider,
        system_instruction: str,
        user_message: str,
        history: list[ChatMessage] | None = None,
        *,
        max_output_tokens: int | None = None,
        timeout_seconds: float | None = None,
        response_mime_type: str | None = None,
    ) -> str | None:
        kwargs: dict[str, Any] = {
            "max_output_tokens": max_output_tokens,
            "timeout_seconds": timeout_seconds,
        }
        if response_mime_type and getattr(provider, "_supports_response_mime_type", False):
            kwargs["response_mime_type"] = response_mime_type
        try:
            return await provider.generate_text(
                system_instruction,
                user_message,
                history,
                **kwargs,
            )
        except AILimitReached:
            raise
        except Exception as error:
            event(
                "llm_route_error",
                error=type(error).__name__,
                model=getattr(provider, "model", None),
            )
            return None

    def tier_for_feature(self, feature: str | None) -> ModelTier:
        normalized = (feature or "").strip().casefold()
        if normalized == "fact_check":
            return ModelTier.BALANCED
        if normalized in FAST_FEATURES:
            return ModelTier.FAST
        if normalized in REASONING_FEATURES:
            return ModelTier.REASONING
        return ModelTier.BALANCED

    def selected_provider(self, *, grounded: bool = False) -> tuple[ModelTier, LLMProvider]:
        feature = (current_model_context().get("feature") or "").strip().casefold()
        if not grounded and feature in LIGHT_FEATURES and self.light_providers:
            provider = self.light_providers[0]
            event(
                "llm_route",
                tier="light",
                provider=getattr(provider, "provider_name", type(provider).__name__),
                model=getattr(provider, "model", None),
            )
            return ModelTier.FAST, provider
        tier = ModelTier.GROUNDED if grounded else self.tier_for_feature(feature)
        provider = self.providers[tier]
        event(
            "llm_route",
            tier=tier.value,
            provider=getattr(provider, "provider_name", type(provider).__name__),
            model=getattr(provider, "model", None),
        )
        return tier, provider

    @guarded
    async def generate_text(
        self,
        system_instruction: str,
        user_message: str,
        history: list[ChatMessage] | None = None,
        *,
        max_output_tokens: int | None = None,
        timeout_seconds: float | None = None,
        response_mime_type: str | None = None,
    ) -> str | None:
        # One wall-clock budget for primary attempts, backoff and model fallback.
        try:
            async with asyncio.timeout(timeout_seconds if timeout_seconds is not None else 20):
                return await self._generate_text_routed(
                    system_instruction,
                    user_message,
                    history,
                    max_output_tokens=max_output_tokens,
                    timeout_seconds=timeout_seconds,
                    response_mime_type=response_mime_type,
                )
        except TimeoutError:
            cast(Any, record_route_deadline)()
            event(
                "llm_route_deadline",
                timeout_seconds=timeout_seconds if timeout_seconds is not None else 20,
            )
            return None

    async def _generate_text_routed(
        self,
        system_instruction: str,
        user_message: str,
        history: list[ChatMessage] | None = None,
        *,
        max_output_tokens: int | None = None,
        timeout_seconds: float | None = None,
        response_mime_type: str | None = None,
    ) -> str | None:
        feature = (current_model_context().get("feature") or "").strip().casefold()
        tier, provider = self.selected_provider()
        fallback_tier = ModelTier.REASONING if tier is ModelTier.BALANCED else ModelTier.BALANCED
        fallback = self.fallback or self.providers[fallback_tier]

        raw_candidates: list[LLMProvider] = [provider]
        if feature in LIGHT_FEATURES and self.light_providers:
            raw_candidates.extend(self.light_providers[1:])
            raw_candidates.append(self.providers[ModelTier.FAST])
        else:
            raw_candidates.extend(self.tier_fallbacks.get(tier, ()))
        raw_candidates.append(fallback)
        if fallback is not self.providers[fallback_tier]:
            raw_candidates.append(self.providers[fallback_tier])
        candidates = self._dedupe_candidates(raw_candidates)

        budget = timeout_seconds if timeout_seconds is not None else 20.0
        started = asyncio.get_running_loop().time()
        last_result: str | None = None
        for index, candidate in enumerate(candidates):
            remaining = budget - (asyncio.get_running_loop().time() - started)
            if remaining <= 0:
                break
            if len(candidates) == 1:
                candidate_budget = remaining
            elif index == 0:
                # Cap primary below half on long multi-fallback budgets so a slow
                # 503 on model 1 cannot starve every fallback model to 2-3 seconds.
                primary_share = 0.45 if budget >= 25.0 and len(candidates) > 2 else 0.70
                candidate_budget = min(remaining, budget * primary_share)
            elif budget >= 15.0:
                candidate_budget = min(remaining, max(12.0, remaining * 0.65))
            else:
                candidate_budget = remaining / max(1, len(candidates) - index)
            if index > 0:
                event(
                    "llm_route_fallback",
                    reason="selected_model_unavailable",
                    from_tier=tier.value,
                    from_model=getattr(candidates[index - 1], "model", None),
                    to_tier=fallback_tier.value,
                    to_model=getattr(candidate, "model", None),
                )
            try:
                async with asyncio.timeout(candidate_budget):
                    result = await self._safe_text(
                        candidate,
                        system_instruction,
                        user_message,
                        history,
                        max_output_tokens=max_output_tokens,
                        timeout_seconds=candidate_budget,
                        response_mime_type=response_mime_type,
                    )
            except TimeoutError:
                if index == 0:
                    event("llm_primary_deadline", model=getattr(candidate, "model", None))
                result = None
            if result is not None and result.strip():
                return result
            last_result = result
        return last_result

    @guarded
    async def grounded_generate(
        self, system_instruction: str, user_message: str, *,
        max_output_tokens: int = 1800, timeout_seconds: float = 45,
    ) -> GroundedReply:
        # Bound all credential, endpoint and model fallbacks together.
        try:
            async with asyncio.timeout(timeout_seconds):
                return await self._grounded_generate_routed(system_instruction, user_message,
                    max_output_tokens=max_output_tokens, timeout_seconds=timeout_seconds)
        except TimeoutError:
            event('llm_grounded_route_deadline', timeout_seconds=timeout_seconds)
            raise GroundingError('Source-backed responses are temporarily unavailable. Please try again later.') from None

    async def _grounded_generate_routed(
        self,
        system_instruction: str,
        user_message: str,
        *,
        max_output_tokens: int = 1800,
        timeout_seconds: float = 45,
    ) -> GroundedReply:
        _, provider = self.selected_provider(grounded=True)
        fallback = self.fallback or self.providers[ModelTier.BALANCED]
        raw_candidates: list[LLMProvider] = [
            provider,
            *self.tier_fallbacks.get(ModelTier.GROUNDED, ()),
            fallback,
        ]
        if fallback is not self.providers[ModelTier.BALANCED]:
            raw_candidates.append(self.providers[ModelTier.BALANCED])
        candidates = self._dedupe_candidates(raw_candidates)
        started = asyncio.get_running_loop().time()
        saw_rate_limit = False
        rate_limit_models = 0
        retry_after: int | None = None
        for index, candidate in enumerate(candidates):
            remaining = timeout_seconds - (asyncio.get_running_loop().time() - started)
            if remaining <= 0:
                break
            candidate_budget = remaining / (len(candidates) - index)
            try:
                async with asyncio.timeout(candidate_budget):
                    return await candidate.grounded_generate(
                        system_instruction, user_message,
                        max_output_tokens=max_output_tokens, timeout_seconds=candidate_budget)
            except AILimitReached:
                raise
            except GroundingRateLimitError as error:
                saw_rate_limit = True
                rate_limit_models += 1
                if error.retry_after_seconds is not None:
                    retry_after = error.retry_after_seconds
                event(
                    "llm_grounded_route_error",
                    error=type(error).__name__,
                    model=getattr(candidate, "model", None),
                )
                # Free-tier google_search 429s apply across models; stop early
                # instead of burning RPM pacing slots across every fallback tier.
                if rate_limit_models >= 2:
                    break
            except Exception as error:
                event(
                    "llm_grounded_route_error",
                    error=type(error).__name__,
                    model=getattr(candidate, "model", None),
                )
        if saw_rate_limit:
            raise GroundingRateLimitError(retry_after)
        raise GroundingError(
            "Source-backed responses are temporarily unavailable. Please try again later."
        )
