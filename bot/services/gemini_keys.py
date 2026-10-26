"""Bounded credential rotation without changing models, prompts or feature rules."""
from dataclasses import dataclass, field
import asyncio
import time

from bot.logging.telemetry import event
from bot.services.llm import LLMProvider, GroundingError


@dataclass(slots=True)
class KeySlot:
    value: str = field(repr=False)
    active: int = 0
    retry_at: float = 0


class GeminiKeyPool:
    """Event-loop-local least-busy rotation; never expose credential values."""

    def __init__(self, keys):
        self.slots = [KeySlot(key) for key in dict.fromkeys(key.strip() for key in keys if key.strip())]
        self.cursor = 0

    def acquire(self, eligible=None):
        candidates = range(len(self.slots)) if eligible is None else eligible
        candidates = [i for i in candidates if self.slots[i].retry_at <= time.monotonic()
                      and not (self.slots[i].retry_at and self.slots[i].active)]
        if not candidates:
            return None
        size = len(self.slots)
        index = min(candidates, key=lambda i: (self.slots[i].active, (i - self.cursor) % size))
        self.cursor = (index + 1) % size
        self.slots[index].active += 1
        return index

    def release(self, index):
        self.slots[index].active = max(0, self.slots[index].active - 1)

    def block(self, index, seconds=300):
        self.slots[index].retry_at = max(self.slots[index].retry_at, time.monotonic() + seconds)

    def success(self, index):
        # Do not erase a newer concurrent rejection of this same credential.
        if self.slots[index].retry_at <= time.monotonic():
            self.slots[index].retry_at = 0

    def snapshot(self):
        return {'configured': len(self.slots),
                'ready': sum(slot.retry_at <= time.monotonic() for slot in self.slots),
                'active': sum(slot.active for slot in self.slots)}


class PooledQuotaView:
    """Read-only health aggregation; admission remains with each project's quota."""

    def __init__(self, services):
        self.quotas = list({id(service.quota): service.quota for service in services}.values())

    async def snapshot(self):
        snapshots = await asyncio.gather(*(quota.snapshot() for quota in self.quotas))
        used = sum(item['daily_used'] for item in snapshots)
        limit = sum(item['daily_limit'] or 0 for item in snapshots)
        unlimited = any(item['daily_limit'] is None for item in snapshots)
        return {'daily_used': used, 'daily_limit': None if unlimited else limit,
                'rpm_limit': sum(item['rpm_limit'] for item in snapshots),
                'daily_percent': round(used * 100 / limit, 1) if limit and not unlimited else None,
                'blocked_seconds': min(item['blocked_seconds'] for item in snapshots),
                'reset_in_seconds': max(item['reset_in_seconds'] for item in snapshots),
                'source': 'pooled-projects' if len(snapshots) > 1 else snapshots[0]['source']}


class GeminiPooledService(LLMProvider):
    """Try a healthy key on the SAME model before the existing model fallback."""

    provider_name = 'gemini'

    def __init__(self, services, key_pool):
        self.services, self.key_pool = services, key_pool
        self.model = services[0].model
        self.thinking_level = services[0].thinking_level
        self.thinking_budget = services[0].thinking_budget
        self.quota = PooledQuotaView(services)

    @property
    def availability(self):
        # Preserve the existing health interface without letting one key mark
        # the whole model unavailable when a different credential is healthy.
        return min((service.availability for service in self.services), key=lambda state: state.retry_at)

    def _eligible(self, tried):
        from bot.services.model_quota import quota_day
        day = quota_day()[0]
        now = time.monotonic()
        return [i for i, service in enumerate(self.services) if i not in tried
                and self.key_pool.slots[i].retry_at <= now
                and not (self.key_pool.slots[i].retry_at and self.key_pool.slots[i].active)
                and service.availability.retry_at <= now and not service.availability.probing
                and service.quota.blocked_until <= time.time()
                and not (service.quota.rpd and service.quota.day == day
                         and service.quota.daily >= service.quota.rpd)]

    async def _run(self, operation, system_instruction, user_message, **kwargs):
        from bot.services.gemini import current_gemini_failure
        budget = kwargs.pop('timeout_seconds', None)
        budget = budget if budget is not None else (45 if operation == 'grounded_generate' else 20)
        deadline = time.monotonic() + budget
        tried = set()
        last_error = None
        while len(tried) < len(self.services):
            eligible = self._eligible(tried)
            index = self.key_pool.acquire(eligible)
            if index is None:
                break
            tried.add(index)
            service = self.services[index]
            remaining = deadline - time.monotonic()
            slice_seconds = remaining / max(1, len(eligible))
            if slice_seconds <= 0:
                self.key_pool.release(index)
                break
            failure = None
            try:
                async with asyncio.timeout(slice_seconds):
                    result = await getattr(service, operation)(system_instruction, user_message,
                        timeout_seconds=slice_seconds, **kwargs)
                if result is not None:
                    self.key_pool.success(index)
                    return result
                failure = current_gemini_failure()
            except TimeoutError:
                service.availability.retry_at = time.monotonic() + 30
                failure = ('transport', 'timeout')
            except GroundingError as error:
                last_error = error
                failure = current_gemini_failure()
            finally:
                self.key_pool.release(index)
            if failure is None:
                break  # Empty/safety output is not a credential failure.
            kind, detail = failure
            if kind == 'http':
                status, category = detail
                if status in {401, 403} or (status == 400 and category == 'api_key'):
                    self.key_pool.block(index)
                elif status not in {429, 500, 502, 503, 504}:
                    break
            elif kind != 'transport':
                if kind != 'quota':
                    break
            event('gemini_key_failover', model=self.model, key_slot=index + 1, reason=kind)
        if operation == 'grounded_generate':
            if last_error is not None:
                raise last_error
            raise GroundingError('Source-backed responses are temporarily unavailable.')
        return None

    async def generate_text(self, system_instruction, user_message, history=None, *,
                            max_output_tokens=None, timeout_seconds=None):
        return await self._run('generate_text', system_instruction, user_message, history=history,
            max_output_tokens=max_output_tokens, timeout_seconds=timeout_seconds)

    async def grounded_generate(self, system_instruction, user_message, *,
                                max_output_tokens=1800, timeout_seconds=45):
        return await self._run('grounded_generate', system_instruction, user_message,
            max_output_tokens=max_output_tokens, timeout_seconds=timeout_seconds)
