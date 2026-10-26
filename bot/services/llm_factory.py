"""The single composition point for text model providers."""

import aiohttp

from bot.config.settings import Settings
from bot.services.gemini import GeminiService, GeminiAvailability
from bot.services.gemini_keys import GeminiKeyPool, GeminiPooledService
from bot.services.llm import LLMProvider
from bot.services.model_router import ModelRouter, ModelTier
from bot.services.model_quota import ModelQuota


def create_llm_provider(
    settings: Settings, http_session: aiohttp.ClientSession, guard=None, *, redis=None
) -> LLMProvider:
    """Preserve feature routes; credentials rotate before the model fallback."""
    provider = settings.llm_provider.strip().casefold()
    if provider != 'gemini':
        raise ValueError(f"Unsupported LLM_PROVIDER: {provider!r}. Available: gemini")
    pool = GeminiKeyPool(settings.gemini_keys)
    availability, quotas = {}, {}

    def build(model, *, thinking_budget=None, thinking_level=None):
        services = []
        # Preserve legacy missing-key behavior and the one-key public interface.
        for index, key in enumerate(settings.gemini_keys or ('',)):
            service = GeminiService(key, model, http_session,
                thinking_budget=thinking_budget, thinking_level=thinking_level)
            canonical = model.removeprefix('models/')
            service.availability = availability.setdefault((canonical, index), GeminiAvailability())
            namespace = settings.gemini_quota_namespace
            if key == settings.gemini_api_key_2.strip() and key != settings.gemini_api_key.strip():
                namespace = settings.gemini_secondary_quota_namespace.strip() or namespace
            identity = (namespace, canonical)
            if identity not in quotas:
                limits = settings.gemini_model_limits.get(canonical, {'rpm': 5, 'rpd': 20})
                quotas[identity] = ModelQuota(**limits, redis=redis, model=canonical,
                    namespace=namespace, max_wait=settings.gemini_pacing_wait_seconds)
            service.quota = quotas[identity]
            services.append(service)
        return services[0] if len(services) == 1 else GeminiPooledService(services, pool)

    providers = {
        ModelTier.FAST: build(settings.gemini_fast_model, thinking_level='minimal'),
        ModelTier.BALANCED: build(settings.gemini_model, thinking_level='minimal'),
        ModelTier.REASONING: build(settings.gemini_reasoning_model, thinking_level='low'),
        ModelTier.GROUNDED: build(settings.gemini_grounded_model, thinking_budget=0),
    }
    fallback = build(settings.gemini_fallback_model, thinking_level='minimal') if settings.gemini_fallback_model else None
    router = ModelRouter(providers, guard=guard, fallback=fallback)
    router.key_pool = pool
    return router
