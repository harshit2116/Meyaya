"""The single composition point for text model providers."""

from __future__ import annotations

from typing import Any, cast

import aiohttp

from bot.config.settings import Settings
from bot.services.gemini import GeminiService, GeminiAvailability
from bot.services.gemini_keys import GeminiKeyPool, GeminiPooledService
from bot.services.llm import LLMProvider
from bot.services.model_router import ModelRouter, ModelTier
from bot.services.model_quota import ModelQuota


def create_llm_provider(
    settings: Settings,
    http_session: aiohttp.ClientSession,
    guard: Any = None,
    *,
    redis: Any = None,
) -> LLMProvider:
    """Preserve feature routes; credentials rotate before the model fallback."""
    provider = settings.llm_provider.strip().casefold()
    if provider != 'gemini':
        raise ValueError(f"Unsupported LLM_PROVIDER: {provider!r}. Available: gemini")
    pool = cast(Any, GeminiKeyPool)(settings.gemini_keys)
    availability: dict[tuple[str, int], GeminiAvailability] = {}
    quotas: dict[tuple[str, str], ModelQuota] = {}
    pooled_views: dict[tuple[int, ...], Any] = {}

    def build(
        model: str,
        *,
        thinking_budget: int | None = None,
        thinking_level: str | None = None,
    ) -> LLMProvider:
        services: list[GeminiService] = []
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
            cast(Any, service).quota = quotas[identity]
            services.append(service)
        if len(services) == 1:
            return services[0]
        pooled = cast(Any, GeminiPooledService)(services, pool)
        view_key = tuple(id(s.quota) for s in services)
        pooled.quota = pooled_views.setdefault(view_key, pooled.quota)
        return cast(LLMProvider, pooled)

    def _grounded_thinking(model: str) -> tuple[int | None, str | None]:
        canonical = model.removeprefix("models/")
        if canonical.startswith(("gemini-3", "gemini-4")):
            return None, "minimal"
        return 0, None

    grounded_budget, grounded_level = _grounded_thinking(settings.gemini_grounded_model)
    providers = {
        ModelTier.FAST: build(settings.gemini_fast_model, thinking_level='minimal'),
        ModelTier.BALANCED: build(settings.gemini_model, thinking_level='minimal'),
        ModelTier.REASONING: build(settings.gemini_reasoning_model, thinking_level='low'),
        ModelTier.GROUNDED: build(
            settings.gemini_grounded_model,
            thinking_budget=grounded_budget,
            thinking_level=grounded_level,
        ),
    }
    tier_fallbacks: dict[ModelTier, list[LLMProvider]] = {
        ModelTier.REASONING: [
            build(model, thinking_level='low')
            for model in getattr(settings, 'gemini_reasoning_fallback_models', ())
            if model and model != settings.gemini_reasoning_model
        ],
        ModelTier.GROUNDED: [
            build(model, thinking_budget=_grounded_thinking(model)[0], thinking_level=_grounded_thinking(model)[1])
            for model in getattr(settings, 'gemini_grounded_fallback_models', ())
            if model and model != settings.gemini_grounded_model
        ],
    }
    light_models = [
        model
        for model in (
            getattr(settings, 'gemini_light_model', ''),
            *getattr(settings, 'gemini_light_fallback_models', ()),
        )
        if model
    ]
    light_providers = [build(model, thinking_level='minimal') for model in dict.fromkeys(light_models)]
    fallback = build(settings.gemini_fallback_model, thinking_level='minimal') if settings.gemini_fallback_model else None
    router = ModelRouter(
        providers,
        guard=guard,
        fallback=fallback,
        tier_fallbacks=tier_fallbacks,
        light_providers=light_providers,
    )
    router.key_pool = pool
    return router
