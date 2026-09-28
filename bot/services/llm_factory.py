"""The single composition point for text model providers."""

import aiohttp

from bot.config.settings import Settings
from bot.services.gemini import GeminiService, GeminiAvailability
from bot.services.llm import LLMProvider
from bot.services.model_router import ModelRouter, ModelTier


def create_llm_provider(
    settings: Settings, http_session: aiohttp.ClientSession, guard=None
) -> LLMProvider:
    """Build feature routes while keeping credentials and SDKs out of commands."""
    provider = settings.llm_provider.strip().casefold()
    if provider == "gemini":
        providers: dict[ModelTier, LLMProvider] = {
            ModelTier.FAST: GeminiService(
                settings.gemini_api_key,
                settings.gemini_fast_model,
                http_session,
                thinking_budget=None,
                thinking_level="minimal",
            ),
            ModelTier.BALANCED: GeminiService(
                settings.gemini_api_key,
                settings.gemini_model,
                http_session,
                thinking_budget=None,
                thinking_level="minimal",
            ),
            ModelTier.REASONING: GeminiService(
                settings.gemini_api_key,
                settings.gemini_reasoning_model,
                http_session,
                thinking_budget=None,
                thinking_level="low",
            ),
            ModelTier.GROUNDED: GeminiService(
                settings.gemini_api_key,
                settings.gemini_grounded_model,
                http_session,
                thinking_budget=0,
            ),
        }
        fallback = (
            GeminiService(
                settings.gemini_api_key,
                settings.gemini_fallback_model,
                http_session,
                thinking_budget=None,
                thinking_level="minimal",
            )
            if settings.gemini_fallback_model
            else None
        )
        # FAST and BALANCED often use the same model; share bounded cooldown state.
        availability = {}
        for service in (*providers.values(), *((fallback,) if fallback else ())):
            service.availability = availability.setdefault(service.model, GeminiAvailability())
        return ModelRouter(providers, guard=guard, fallback=fallback)
    raise ValueError(f"Unsupported LLM_PROVIDER: {provider!r}. Available: gemini")
