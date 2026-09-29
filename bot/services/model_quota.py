"""Small per-model attempt budgets; Redis preserves counts across restarts."""

import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import logging
import time
from uuid import uuid4
from zoneinfo import ZoneInfo

from redis.exceptions import RedisError

logger = logging.getLogger(__name__)
PACIFIC = ZoneInfo('America/Los_Angeles')

RESERVE = """
local t = redis.call('TIME')
local now = tonumber(t[1]) + tonumber(t[2]) / 1000000
local blocked = tonumber(redis.call('GET', KEYS[3]) or '0')
if blocked > now then return {3, math.ceil((blocked-now)*1000)} end
local daily = tonumber(redis.call('GET', KEYS[2]) or '0')
if tonumber(ARGV[2]) > 0 and daily >= tonumber(ARGV[2]) then return {2, 0} end
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now-60)
local last = redis.call('ZREVRANGE', KEYS[1], 0, 0, 'WITHSCORES')
local wait = 0
if #last > 0 then wait = tonumber(last[2]) + 60/tonumber(ARGV[1]) - now end
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[1]) then
  local first = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
  wait = math.max(wait, tonumber(first[2])+60-now)
end
if wait > 0 then return {1, math.ceil(wait*1000)} end
redis.call('ZADD', KEYS[1], now, ARGV[3])
redis.call('EXPIRE', KEYS[1], 120)
redis.call('INCR', KEYS[2])
redis.call('EXPIRE', KEYS[2], ARGV[4])
return {0, 0}
"""


def quota_day():
    now = datetime.now(timezone.utc)
    local = now.astimezone(PACIFIC)
    reset = datetime.combine(local.date() + timedelta(days=1), datetime.min.time(), PACIFIC)
    return local.date().isoformat(), (reset.astimezone(timezone.utc) - now).total_seconds()


class ModelQuota:
    def __init__(self, rpm=5, rpd=20, *, redis=None, namespace='meyaya', model='', max_wait=6):
        self.rpm, self.rpd = rpm, rpd
        self.redis, self.max_wait = redis, max_wait
        identity = sha256(f'{namespace}:{model}'.encode()).hexdigest()[:24]
        self.prefix = f'meyaya:model-quota:{{{identity}}}'
        self.lock = asyncio.Lock()
        self.recent = deque(maxlen=rpm)
        self.day, self.daily = '', 0
        self.blocked_until = 0
        self.redis_retry_at = 0

    def _local_reserve(self, day):
        now = time.monotonic()
        if self.day != day:
            self.day, self.daily = day, 0
        if time.time() < self.blocked_until:
            return 3, (self.blocked_until - time.time()) * 1000
        if self.rpd and self.daily >= self.rpd:
            return 2, 0
        while self.recent and self.recent[0] <= now - 60:
            self.recent.popleft()
        wait = max(0, self.recent[-1] + 60 / self.rpm - now) if self.recent else 0
        if len(self.recent) >= self.rpm:
            wait = max(wait, self.recent[0] + 60 - now)
        if wait > 0:
            return 1, wait * 1000
        self.recent.append(now)
        self.daily += 1
        return 0, 0

    async def acquire(self, *, optional=False):
        if time.time() < self.blocked_until:
            return 'model_rate_backoff'
        if optional:
            return await self._acquire(optional=True)
        try:
            async with asyncio.timeout(max(.001, self.max_wait)):
                return await self._acquire(optional=False)
        except TimeoutError:
            return 'model_pacing_busy'

    async def _acquire(self, *, optional=False):
        # Admission is already bounded by AIGuard. No background workers or
        # unbounded per-message timers; the router deadline includes this wait.
        deadline = time.monotonic() + (0 if optional else self.max_wait)
        if optional and self.lock.locked():
            return 'model_pacing_busy'
        async with self.lock:
            while True:
                day, reset_seconds = quota_day()
                if self.redis is not None and time.monotonic() >= self.redis_retry_at:
                    try:
                        async with asyncio.timeout(1):
                            code, wait_ms = await self.redis.eval(
                                RESERVE, 3, self.prefix + ':minute', self.prefix + ':day:' + day,
                                self.prefix + ':blocked', self.rpm, self.rpd, uuid4().hex,
                                int(reset_seconds) + 3600)
                        if code == 0:
                            # Keep a conservative local mirror if Redis disappears.
                            if self.day != day:
                                self.day, self.daily = day, 0
                            self.daily += 1
                            self.recent.append(time.monotonic())
                    except (RedisError, TimeoutError):
                        self.redis_retry_at = time.monotonic() + 60
                        logger.warning('Model quota Redis unavailable; using process-local attempt budget')
                        code, wait_ms = self._local_reserve(day)
                else:
                    code, wait_ms = self._local_reserve(day)
                if code == 0:
                    return None
                if code == 2:
                    self.day, self.daily = day, self.rpd
                    return 'model_daily_budget'
                if code == 3:
                    return 'model_rate_backoff'
                wait = wait_ms / 1000 + .01
                if optional or time.monotonic() + wait > deadline:
                    return 'model_pacing_busy'
                await asyncio.sleep(wait)

    async def block(self, seconds):
        until = time.time() + max(1, seconds)
        self.blocked_until = max(self.blocked_until, until)
        if self.redis is not None and time.monotonic() >= self.redis_retry_at:
            try:
                async with asyncio.timeout(1):
                    await self.redis.eval(
                        "local old=tonumber(redis.call('GET',KEYS[1]) or '0'); "
                        "if tonumber(ARGV[1])>old then redis.call('SET',KEYS[1],ARGV[1],'EX',ARGV[2]) end; return 1",
                        1, self.prefix + ':blocked', until, int(seconds) + 2)
            except (RedisError, TimeoutError):
                self.redis_retry_at = time.monotonic() + 60

    async def snapshot(self):
        """Read-only budget view; opening the dashboard must not reserve quota."""
        day, reset_seconds = quota_day()
        daily = self.daily if self.day == day else 0
        blocked = self.blocked_until
        source = 'process-local'
        if self.redis is not None and time.monotonic() >= self.redis_retry_at:
            try:
                async with asyncio.timeout(1):
                    values = await self.redis.mget(self.prefix + ':day:' + day, self.prefix + ':blocked')
                daily, blocked = max(daily, int(values[0] or 0)), max(blocked, float(values[1] or 0))
                source = 'redis'
            except (RedisError, TimeoutError, ValueError, TypeError):
                pass
        return {'daily_used': daily, 'daily_limit': self.rpd or None, 'rpm_limit': self.rpm,
                'daily_percent': round(daily * 100 / self.rpd, 1) if self.rpd else None,
                'blocked_seconds': round(max(0, blocked - time.time()), 1),
                'reset_in_seconds': round(reset_seconds), 'source': source}
