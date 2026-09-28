"""Feature-aware model selection behind the provider-neutral interface."""

from __future__ import annotations

from enum import StrEnum
import asyncio

from bot.logging.telemetry import current_model_context, event
from bot.services.llm import ChatMessage, GroundedReply, LLMProvider
from bot.services.llm import GroundingError
from bot.services.ai_guard import guarded, AILimitReached


class ModelTier(StrEnum):
    FAST = "fast"
    BALANCED = "balanced"
    REASONING = "reasoning"
    GROUNDED = "grounded"


FAST_FEATURES = frozenset(
    {
        "monitor",
        "moderation",
        "proactive",
        "rate",
        "fun",
        "roast",
        "compliment",
        "rank",
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
    """Select a configured provider/model for each feature and operation."""

    provider_name = "router"
    model = "feature-routed"

    def __init__(
        self, providers: dict[ModelTier, LLMProvider], *, guard=None, fallback=None
    ) -> None:
        required = {ModelTier.FAST, ModelTier.BALANCED, ModelTier.REASONING, ModelTier.GROUNDED}
        missing = required.difference(providers)
        if missing:
            raise ValueError(f"Missing model tiers: {sorted(tier.value for tier in missing)}")
        self.providers = providers
        self.guard = guard
        self.fallback = fallback

    async def _safe_text(self, provider, *args, **kwargs):
        try:
            return await provider.generate_text(*args, **kwargs)
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
            return ModelTier.GROUNDED
        if normalized in FAST_FEATURES:
            return ModelTier.FAST
        if normalized in REASONING_FEATURES:
            return ModelTier.REASONING
        return ModelTier.BALANCED

    def selected_provider(self, *, grounded: bool = False) -> tuple[ModelTier, LLMProvider]:
        feature = current_model_context().get("feature")
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
        timeout_seconds: int | None = None,
    ) -> str | None:
        # One wall-clock budget for primary attempts, backoff and model fallback.
        try:
            async with asyncio.timeout(timeout_seconds if timeout_seconds is not None else 20):
                return await self._generate_text_routed(
                    system_instruction, user_message, history,
                    max_output_tokens=max_output_tokens, timeout_seconds=timeout_seconds)
        except TimeoutError:
            event("llm_route_deadline", timeout_seconds=timeout_seconds if timeout_seconds is not None else 20)
            return None

    async def _generate_text_routed(
        self, system_instruction, user_message, history=None, *,
        max_output_tokens=None, timeout_seconds=None,
    ) -> str | None:
        tier, provider = self.selected_provider()
        result = await self._safe_text(
            provider,
            system_instruction,
            user_message,
            history,
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
        )
        if result is not None and result.strip():
            return result

        fallback_tier = ModelTier.REASONING if tier is ModelTier.BALANCED else ModelTier.BALANCED
        fallback = self.fallback or self.providers[fallback_tier]
        if fallback is provider or getattr(fallback, "model", None) == getattr(
            provider, "model", None
        ):
            return result
        event(
            "llm_route_fallback",
            reason="selected_model_unavailable",
            from_tier=tier.value,
            from_model=getattr(provider, "model", None),
            to_tier=fallback_tier.value,
            to_model=getattr(fallback, "model", None),
        )
        return await self._safe_text(
            fallback,
            system_instruction,
            user_message,
            history,
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
        )

    @guarded
    async def grounded_generate(
        self,
        system_instruction: str,
        user_message: str,
        *,
        max_output_tokens: int = 1800,
        timeout_seconds: int = 45,
    ) -> GroundedReply:
        _, provider = self.selected_provider(grounded=True)
        fallback = self.fallback or self.providers[ModelTier.BALANCED]
        candidates = [provider]
        if fallback is not provider and getattr(fallback, "model", None) != getattr(
            provider, "model", None
        ):
            candidates.append(fallback)
        for candidate in candidates:
            try:
                return await candidate.grounded_generate(
                    system_instruction,
                    user_message,
                    max_output_tokens=max_output_tokens,
                    timeout_seconds=timeout_seconds,
                )
            except AILimitReached:
                raise
            except Exception as error:
                event(
                    "llm_grounded_route_error",
                    error=type(error).__name__,
                    model=getattr(candidate, "model", None),
                )
        raise GroundingError(
            "Source-backed responses are temporarily unavailable. Please try again later."
        )
