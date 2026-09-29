"""On-demand, cached health checks using existing clients and observed outcomes."""

import asyncio
import math
import time
from datetime import UTC, datetime
from sqlalchemy import select

from bot.logging.health import health


class OwnerHealth:
    def __init__(self, bot):
        self.bot = bot
        self.lock = asyncio.Lock()
        self.cache = None
        self.cached_at = 0

    async def _probe(self, name, callback):
        started = time.perf_counter()
        try:
            async with asyncio.timeout(2):
                await callback()
            return {'name': name, 'status': 'healthy',
                    'latency_ms': round((time.perf_counter() - started) * 1000, 1)}
        except Exception as error:
            return {'name': name, 'status': 'unavailable', 'latency_ms': None,
                    'reason': type(error).__name__}

    async def _database(self):
        async with self.bot.session_factory() as session:
            await session.execute(select(1))

    async def _dependencies(self):
        # Coalesce simultaneous tabs and cap dependency traffic to once / 30s.
        async with self.lock:
            if self.cache is not None and time.monotonic() - self.cached_at < 30:
                return self.cache
            checks = [self._probe('PostgreSQL', self._database)]
            redis = getattr(self.bot, 'redis', None)
            if redis is not None:
                checks.append(self._probe('Redis', redis.ping))
            dependencies = list(await asyncio.gather(*checks))
            if redis is None:
                dependencies.append({'name': 'Redis', 'status': 'disabled', 'latency_ms': None})
            provider = getattr(self.bot, '_llm_provider', None)
            services = list(getattr(provider, 'providers', {}).items())
            if getattr(provider, 'fallback', None):
                services.append(('fallback', provider.fallback))
            quotas = {service.model.removeprefix('models/'): service.quota
                      for _, service in services if getattr(service, 'quota', None)}
            results = await asyncio.gather(*(quota.snapshot() for quota in quotas.values()), return_exceptions=True)
            budget = {model: result for model, result in zip(quotas, results) if isinstance(result, dict)}
            self.cached_at = time.monotonic()
            self.cache = (dependencies, budget, time.time())
            return self.cache

    def _model(self, label, model, budget, service=None, *, configured=True):
        model = str(model or '').removeprefix('models/')
        observation = health.models.get(model)
        quota = budget.get(model)
        status, reason = 'unknown', 'No recent request observed'
        if observation and time.time() - observation['observed_at'] < 900:
            status = 'healthy' if observation['status'] == 'success' else 'degraded'
            reason = observation.get('reason') or observation['status']
        availability = getattr(service, 'availability', None)
        if availability is not None and availability.retry_at > time.monotonic():
            status, reason = 'degraded', 'Provider cooldown'
        if quota and (quota['blocked_seconds'] > 0 or (quota['daily_percent'] or 0) >= 80):
            status, reason = 'degraded', 'Quota backoff or daily budget nearing its limit'
        if quota and (quota['daily_percent'] or 0) >= 100:
            status, reason = 'unavailable', 'Daily budget exhausted'
        if not configured:
            status, reason = 'disabled', 'AI paused or not configured'
        return {'name': label, 'model': model or None, 'status': status, 'reason': reason,
                'quota': quota, 'last_observation': observation}

    async def snapshot(self):
        dependencies, budgets, checked_at = await self._dependencies()
        bot, settings = self.bot, self.bot.settings
        ready = bool(bot.is_ready())
        latency = getattr(bot, 'latency', None)
        latency = round(latency * 1000, 1) if isinstance(latency, (int, float)) and math.isfinite(latency) else None
        provider = getattr(bot, '_llm_provider', None)
        configured = bool(getattr(settings, 'ai_enabled', False) and getattr(settings, 'gemini_api_key', ''))
        names = {'fast': 'Gemini Fast', 'balanced': 'Gemini Flash',
                 'reasoning': 'Gemini Reason', 'grounded': 'Gemini Grounded'}
        models = [self._model(names.get(str(tier), 'Gemini Fallback'), service.model, budgets,
                              service, configured=configured)
                  for tier, service in getattr(provider, 'providers', {}).items()]
        if getattr(provider, 'fallback', None):
            models.append(self._model('Gemini Fallback', provider.fallback.model, budgets,
                                      provider.fallback, configured=configured))
        models.append(self._model('Gemini Live', getattr(settings, 'gemini_live_model', None), {}, configured=configured))
        guard = getattr(bot, 'ai_guard', None)
        return {'generated_at': datetime.now(UTC).isoformat(), 'checks_at': checked_at,
                'scope': 'process', 'started_at': datetime.fromtimestamp(health.started_at, UTC).isoformat(),
                'uptime_seconds': round(time.time() - health.started_at),
                'dependencies': [{'name': 'Discord', 'status': 'healthy' if ready else 'unavailable',
                                  'latency_ms': latency, 'reason': 'Gateway heartbeat'}] + dependencies,
                'models': models, 'host': dict(health.host),
                'queue': {'active': getattr(guard, 'active', 0), 'waiting': getattr(guard, 'waiting', 0),
                          'active_limit': getattr(settings, 'ai_max_concurrent', 0),
                          'waiting_limit': getattr(settings, 'ai_queue_size', 0),
                          'voice_active': len(getattr(guard, 'voice_guilds', ()))},
                'guilds': len(bot.guilds), 'users_seen': len(health.users), 'users_seen_capped': health.users_capped,
                'users_cached': len(getattr(bot, 'users', ())),
                'errors_24h': health.counts(), 'recent_errors': health.search()}
