"""The single composition point for text model providers."""

import aiohttp

from bot.config.settings import Settings
from bot.services.gemini import GeminiService
from bot.services.llm import LLMProvider
from bot.services.model_router import ModelRouter, ModelTier


def create_llm_provider(settings: Settings, http_session: aiohttp.ClientSession) -> LLMProvider:
    """Build feature routes while keeping credentials and SDKs out of commands."""
    provider = settings.llm_provider.strip().casefold()
    if provider == "gemini":
        providers: dict[ModelTier, LLMProvider] = {
            ModelTier.FAST: GeminiService(
                settings.gemini_api_key,
                settings.gemini_fast_model,
                http_session,
                thinking_budget=0,
            ),
            ModelTier.BALANCED: GeminiService(
                settings.gemini_api_key,
                settings.gemini_model,
                http_session,
                thinking_budget=0,
            ),
            ModelTier.REASONING: GeminiService(
                settings.gemini_api_key,
                settings.gemini_reasoning_model,
                http_session,
                # Gemini 2.5 Pro cannot disable thinking; 128 is its documented
                # minimum and leaves room for the bounded JSON response.
                thinking_budget=128,
            ),
            ModelTier.GROUNDED: GeminiService(
                settings.gemini_api_key,
                settings.gemini_grounded_model,
                http_session,
                thinking_budget=0,
            ),
        }
        return ModelRouter(providers)
    raise ValueError(f"Unsupported LLM_PROVIDER: {provider!r}. Available: gemini")
