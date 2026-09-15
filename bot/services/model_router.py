"""Feature-aware model selection behind the provider-neutral interface."""

from __future__ import annotations

from enum import StrEnum

from bot.logging.telemetry import current_model_context, event
from bot.services.llm import ChatMessage, GroundedReply, LLMProvider


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
        "legacy",
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

    def __init__(self, providers: dict[ModelTier, LLMProvider]) -> None:
        required = {ModelTier.FAST, ModelTier.BALANCED, ModelTier.REASONING, ModelTier.GROUNDED}
        missing = required.difference(providers)
        if missing:
            raise ValueError(f"Missing model tiers: {sorted(tier.value for tier in missing)}")
        self.providers = providers

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

    async def generate_text(
        self,
        system_instruction: str,
        user_message: str,
        history: list[ChatMessage] | None = None,
        *,
        max_output_tokens: int | None = None,
        timeout_seconds: int | None = None,
    ) -> str | None:
        tier, provider = self.selected_provider()
        result = await provider.generate_text(
            system_instruction,
            user_message,
            history,
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
        )
        if result is not None or tier is ModelTier.BALANCED:
            return result

        fallback = self.providers[ModelTier.BALANCED]
        if fallback is provider:
            return result
        event(
            "llm_route_fallback",
            reason="selected_model_unavailable",
            from_tier=tier.value,
            from_model=getattr(provider, "model", None),
            to_tier=ModelTier.BALANCED.value,
            to_model=getattr(fallback, "model", None),
        )
        return await fallback.generate_text(
            system_instruction,
            user_message,
            history,
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
        )

    async def grounded_generate(
        self,
        system_instruction: str,
        user_message: str,
        *,
        max_output_tokens: int = 1800,
        timeout_seconds: int = 45,
    ) -> GroundedReply:
        _, provider = self.selected_provider(grounded=True)
        return await provider.grounded_generate(
            system_instruction,
            user_message,
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
        )
