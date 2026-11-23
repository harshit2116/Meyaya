"""Semantic memory and server-lore recall powered by Gemini Embeddings."""

from __future__ import annotations

from array import array
import asyncio
from collections import OrderedDict
from collections.abc import Sequence
from hashlib import sha256
import logging
import math
import time
from typing import Any

import aiohttp
from redis.exceptions import RedisError

from bot.services.gemini_keys import GeminiKeyPool

logger = logging.getLogger(__name__)

GEMINI_EMBED_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"
EMBEDDING_DIMENSIONS = 768
EMBEDDING_CACHE_TTL_SECONDS = 30 * 86_400
LOCAL_CACHE_MAX_ITEMS = 512
EMBED_TIMEOUT_SECONDS = 4.0
KEY_COOLDOWN_SECONDS = 60.0
PREFERRED_RELATIONS = frozenset({"preferred_name", "chat_capitalization", "chat_style"})


def _normalize(values: Sequence[float]) -> tuple[float, ...]:
    norm = math.sqrt(math.fsum(v * v for v in values))
    if norm <= 0.0:
        return ()
    return tuple(v / norm for v in values)


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(math.fsum(x * y for x, y in zip(a, b, strict=True)))


class GeminiEmbeddingService:
    """Bounded, Redis-cached semantic reranker for permanent memories and server lore."""

    def __init__(
        self,
        api_keys: tuple[str, ...],
        models: Sequence[str],
        http_session: aiohttp.ClientSession,
        *,
        redis: Any = None,
        key_pool: GeminiKeyPool | None = None,
    ) -> None:
        self.api_keys = tuple(dict.fromkeys(k.strip() for k in api_keys if k.strip()))
        self.models = tuple(
            dict.fromkeys(m.removeprefix("models/").strip() for m in models if m and m.strip())
        )
        self.http_session = http_session
        self.redis = redis
        self.key_pool = key_pool or GeminiKeyPool(self.api_keys)
        self._cache: OrderedDict[str, tuple[float, ...]] = OrderedDict()
        self._blocked_until: dict[tuple[str, int], float] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.api_keys and self.models)

    @staticmethod
    def _digest(text: str) -> str:
        return sha256(text.encode("utf-8")).hexdigest()[:24]

    def _put_local(self, key: str, vector: tuple[float, ...]) -> None:
        self._cache[key] = vector
        self._cache.move_to_end(key)
        while len(self._cache) > LOCAL_CACHE_MAX_ITEMS:
            self._cache.popitem(last=False)

    async def _get_cached(self, text: str) -> tuple[float, ...] | None:
        digest = self._digest(text)
        cached = self._cache.get(digest)
        if cached is not None:
            self._cache.move_to_end(digest)
            return cached
        if self.redis is None:
            return None
        try:
            raw = await self.redis.get(f"meyaya:emb:v1:{digest}")
        except RedisError:
            return None
        if not raw:
            return None
        try:
            if isinstance(raw, str):
                raw_bytes = bytes.fromhex(raw)
            else:
                raw_bytes = bytes(raw)
            arr = array("f")
            arr.frombytes(raw_bytes)
            vector = tuple(arr)
            if vector:
                self._put_local(digest, vector)
                return vector
        except (ValueError, TypeError):
            return None
        return None

    async def _store_cached(self, text: str, vector: tuple[float, ...]) -> None:
        digest = self._digest(text)
        self._put_local(digest, vector)
        if self.redis is None:
            return
        try:
            raw_hex = array("f", vector).tobytes().hex()
            await self.redis.set(f"meyaya:emb:v1:{digest}", raw_hex, ex=EMBEDDING_CACHE_TTL_SECONDS)
        except RedisError:
            return

    async def embed_text(
        self,
        text: str,
        *,
        use_cache: bool = True,
        timeout_seconds: float = EMBED_TIMEOUT_SECONDS,
    ) -> tuple[float, ...] | None:
        """Return a unit-normalized embedding vector or None if unavailable."""

        clean = " ".join(text.split()).strip()[:1000]
        if not self.enabled or not clean:
            return None
        if use_cache:
            cached = await self._get_cached(clean)
            if cached is not None:
                return cached

        for model in self.models:
            payload = {
                "model": f"models/{model}",
                "content": {"parts": [{"text": clean}]},
                "outputDimensionality": EMBEDDING_DIMENSIONS,
            }
            url = GEMINI_EMBED_ENDPOINT.format(model=model)
            tried: set[int] = set()
            now = time.monotonic()
            while len(tried) < len(self.key_pool.slots):
                eligible = [
                    i
                    for i in range(len(self.key_pool.slots))
                    if i not in tried and self._blocked_until.get((model, i), 0.0) <= now
                ]
                index = self.key_pool.acquire(eligible)
                if index is None:
                    break
                tried.add(index)
                key = self.key_pool.slots[index].value
                try:
                    async with asyncio.timeout(timeout_seconds):
                        async with self.http_session.post(
                            url,
                            json=payload,
                            headers={
                                "Content-Type": "application/json",
                                "x-goog-api-key": key,
                            },
                            timeout=aiohttp.ClientTimeout(total=timeout_seconds),
                        ) as response:
                            if response.status in {401, 403}:
                                self.key_pool.block(index)
                                continue
                            if response.status == 429:
                                self._blocked_until[(model, index)] = (
                                    time.monotonic() + KEY_COOLDOWN_SECONDS
                                )
                                continue
                            if response.status != 200:
                                if response.status in {500, 502, 503, 504}:
                                    continue
                                break
                            data = await response.json()
                            self.key_pool.success(index)
                except (aiohttp.ClientError, TimeoutError, ValueError):
                    continue
                finally:
                    self.key_pool.release(index)

                values = (
                    data.get("embedding", {}).get("values") if isinstance(data, dict) else None
                )
                if isinstance(values, list) and values:
                    vector = _normalize([float(v) for v in values])
                    if vector:
                        if use_cache:
                            await self._store_cached(clean, vector)
                        return vector
        return None

    async def rerank_memories(
        self,
        query: str,
        records: Sequence[Any],
        *,
        limit: int = 24,
    ) -> list[Any]:
        """Semantically rank permanent memories while keeping preferred profile keys first."""

        items = list(records)
        if not self.enabled or not query.strip() or len(items) <= 4:
            return items[:limit]

        preferred = [r for r in items if getattr(r, "relation", None) in PREFERRED_RELATIONS]
        candidates = [r for r in items if getattr(r, "relation", None) not in PREFERRED_RELATIONS]
        if len(candidates) <= 2:
            return (preferred + candidates)[:limit]

        try:
            async with asyncio.timeout(5.0):
                query_vec = await self.embed_text(query, use_cache=False, timeout_seconds=3.0)
                if not query_vec:
                    return items[:limit]
                texts = [
                    f"{getattr(r, 'category', '')} {getattr(r, 'relation', '')}: {getattr(r, 'value', '')}"
                    for r in candidates
                ]
                vectors = await asyncio.gather(
                    *(self.embed_text(text, use_cache=True, timeout_seconds=3.0) for text in texts),
                    return_exceptions=True,
                )
        except TimeoutError:
            return items[:limit]

        scored: list[tuple[float, int, Any]] = []
        total = max(1, len(candidates))
        for idx, (record, vec) in enumerate(zip(candidates, vectors, strict=True)):
            sim = _cosine(query_vec, vec) if isinstance(vec, tuple) else 0.0
            # Blend semantic similarity with a gentle recency/keyword prior.
            prior = (total - idx) / total * 0.15
            scored.append((sim + prior, -idx, record))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return (preferred + [item[2] for item in scored])[:limit]

    async def rerank_lore(
        self,
        query: str,
        records: Sequence[Any],
        *,
        limit: int = 12,
    ) -> list[Any]:
        """Semantically surface the most relevant guild lore for the current message."""

        items = list(records)
        if not self.enabled or not query.strip() or len(items) <= 4:
            return items[:limit]

        try:
            async with asyncio.timeout(5.0):
                query_vec = await self.embed_text(query, use_cache=False, timeout_seconds=3.0)
                if not query_vec:
                    return items[:limit]
                vectors = await asyncio.gather(
                    *(
                        self.embed_text(str(getattr(r, "content", "")), use_cache=True, timeout_seconds=3.0)
                        for r in items
                    ),
                    return_exceptions=True,
                )
        except TimeoutError:
            return items[:limit]

        scored: list[tuple[float, int, Any]] = []
        total = max(1, len(items))
        for idx, (record, vec) in enumerate(zip(items, vectors, strict=True)):
            sim = _cosine(query_vec, vec) if isinstance(vec, tuple) else 0.0
            prior = (total - idx) / total * 0.15
            scored.append((sim + prior, -idx, record))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in scored][:limit]
