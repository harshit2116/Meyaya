"""Task-local request metrics. Never log prompts, answers, credentials or evidence."""

from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from functools import wraps
import json
import logging
import time
from uuid import uuid4

logger = logging.getLogger("meyaya.telemetry")
_context: ContextVar[dict | None] = ContextVar("llm_context", default=None)
_metrics: ContextVar[dict | None] = ContextVar("llm_metrics", default=None)


class OperationalTelemetry:
    """Bounded, process-local aggregates containing no request or response text."""

    def __init__(self, capacity: int = 2_000) -> None:
        self.started_at = datetime.now(UTC)
        self._requests: deque[dict] = deque(maxlen=capacity)

    def record(self, payload: dict) -> None:
        if payload.get("event") != "llm_request":
            return
        self._requests.append(
            {
                "recorded_at": datetime.now(UTC),
                "timestamp": payload.get("timestamp"),
                "feature": str(payload.get("feature") or "unspecified")[:80],
                "guild_id": payload.get("guild_id"),
                "channel_id": payload.get("channel_id"),
                "operation": str(payload.get("operation") or "unknown")[:80],
                "provider": str(payload.get("provider") or "unknown")[:80],
                "model": str(payload.get("returned_model") or payload.get("model") or "unknown")[
                    :120
                ],
                "latency_ms": self._number(payload.get("latency_ms")),
                "status": str(payload.get("status") or "unknown")[:32],
                "input_tokens": self._integer(payload.get("input_tokens")),
                "output_tokens": self._integer(payload.get("output_tokens")),
                "total_tokens": self._integer(payload.get("total_tokens")),
                "failed_attempts": self._integer(payload.get("failed_requests")),
                "fallback_reason": (
                    str(payload["fallback_reason"])[:160]
                    if payload.get("fallback_reason")
                    else None
                ),
            }
        )

    def snapshot(self, guild_id: int | None = None) -> dict:
        records = [
            item for item in self._requests if guild_id is None or item["guild_id"] == guild_id
        ]
        latencies = sorted(item["latency_ms"] for item in records if item["latency_ms"] is not None)
        successes = sum(item["status"] == "success" for item in records)
        failures = sum(item["status"] in {"error", "unavailable"} for item in records)
        tokens = sum(item["total_tokens"] or 0 for item in records)
        last_hour = sum(time.time() - item["recorded_at"].timestamp() <= 3_600 for item in records)
        return {
            "scope": "process",
            "started_at": self.started_at.isoformat(),
            "summary": {
                "requests": len(records),
                "successes": successes,
                "failures": failures,
                "recovered_attempts": sum(item["failed_attempts"] for item in records),
                "success_rate": round(successes * 100 / len(records), 1) if records else 0,
                "average_latency_ms": (
                    round(sum(latencies) / len(latencies), 1) if latencies else None
                ),
                "p95_latency_ms": self._percentile(latencies, 0.95),
                "total_tokens": tokens,
                "last_hour": last_hour,
            },
            "features": self._groups(records, "feature"),
            "models": self._groups(records, "model"),
            "recent": [self._public(item) for item in reversed(records[-30:])],
        }

    def guild_summary(self, guild_id: int) -> dict:
        return self.guild_summaries((guild_id,))[guild_id]

    def guild_summaries(self, guild_ids) -> dict[int, dict]:
        """Summarize every visible server in one pass over bounded request history."""

        totals = {
            guild_id: {
                "model_requests": 0,
                "model_failures": 0,
                "model_success_rate": 0,
                "model_tokens": 0,
                "model_average_latency_ms": None,
                "_successes": 0,
                "_latency_total": 0.0,
                "_latency_count": 0,
            }
            for guild_id in guild_ids
        }
        for item in self._requests:
            summary = totals.get(item["guild_id"])
            if summary is None:
                continue
            summary["model_requests"] += 1
            summary["model_failures"] += item["status"] in {"error", "unavailable"}
            summary["_successes"] += item["status"] == "success"
            summary["model_tokens"] += item["total_tokens"] or 0
            if item["latency_ms"] is not None:
                summary["_latency_total"] += item["latency_ms"]
                summary["_latency_count"] += 1
        for summary in totals.values():
            requests = summary["model_requests"]
            successes = summary.pop("_successes")
            latency_total = summary.pop("_latency_total")
            latency_count = summary.pop("_latency_count")
            summary["model_success_rate"] = round(successes * 100 / requests, 1) if requests else 0
            summary["model_average_latency_ms"] = (
                round(latency_total / latency_count, 1) if latency_count else None
            )
        return totals

    @staticmethod
    def _groups(records: list[dict], key: str) -> list[dict]:
        groups: dict[str, dict] = {}
        for item in records:
            name = item[key]
            group = groups.setdefault(
                name,
                {
                    "name": name,
                    "requests": 0,
                    "successes": 0,
                    "failures": 0,
                    "tokens": 0,
                    "latency_total": 0.0,
                    "latency_count": 0,
                },
            )
            group["requests"] += 1
            group["successes"] += item["status"] == "success"
            group["failures"] += item["status"] in {"error", "unavailable"}
            group["tokens"] += item["total_tokens"] or 0
            if item["latency_ms"] is not None:
                group["latency_total"] += item["latency_ms"]
                group["latency_count"] += 1
        result = []
        for group in groups.values():
            latency_total = group.pop("latency_total")
            latency_count = group.pop("latency_count")
            latency = round(latency_total / latency_count, 1) if latency_count else None
            group["average_latency_ms"] = latency
            result.append(group)
        return sorted(result, key=lambda item: (-item["requests"], item["name"]))

    @staticmethod
    def _public(item: dict) -> dict:
        return {
            key: (value.isoformat() if isinstance(value, datetime) else value)
            for key, value in item.items()
            if key != "recorded_at"
        }

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float | None:
        if not values:
            return None
        index = min(len(values) - 1, max(0, round((len(values) - 1) * percentile)))
        return round(values[index], 1)

    @staticmethod
    def _integer(value) -> int:
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    @staticmethod
    def _number(value) -> float | None:
        return (
            float(value)
            if isinstance(value, (int, float)) and not isinstance(value, bool)
            else None
        )


operations = OperationalTelemetry()


def event(name: str, **fields) -> None:
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": name,
        "feature": "unspecified",
        "guild_id": None,
        "channel_id": None,
        **(_context.get() or {}),
        **fields,
    }
    operations.record(payload)
    logger.info(json.dumps(payload, default=str))


@contextmanager
def model_context(
    feature: str, guild_id: int | None, channel_id: int | None, user_id: int | None = None
):
    token = _context.set(
        {"feature": feature, "guild_id": guild_id, "channel_id": channel_id, "user_id": user_id}
    )
    try:
        yield
    finally:
        _context.reset(token)


def current_model_context() -> dict:
    """Return a copy of the active request context for model routing."""

    return dict(_context.get() or {})


def record_response(payload: dict) -> None:
    metrics = _metrics.get()
    if metrics is None:
        return
    usage = payload.get("usageMetadata") or payload.get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    for name, candidates in {
        "input_tokens": ("promptTokenCount", "total_input_tokens"),
        "output_tokens": ("candidatesTokenCount", "total_output_tokens"),
        "total_tokens": ("totalTokenCount", "total_tokens"),
    }.items():
        value = next((usage[k] for k in candidates if isinstance(usage.get(k), int)), None)
        if value is not None:
            metrics[name] = (metrics[name] or 0) + value
    metrics["returned_model"] = payload.get("modelVersion") or payload.get("model")


def request_failure(reason: str, **fields) -> None:
    metrics = _metrics.get()
    if metrics is not None:
        metrics["fallback_reason"] = reason
        metrics["failed_requests"] += 1
    event(
        "llm_attempt_failed", request_id=(metrics or {}).get("request_id"), reason=reason, **fields
    )


def observe(operation: str):
    """Instrument adapter requests, including cancellations and empty results."""

    def decorate(method):
        @wraps(method)
        async def wrapped(self, *args, **kwargs):
            metrics = {
                "request_id": uuid4().hex,
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
                "returned_model": None,
                "failed_requests": 0,
                "fallback_reason": None,
            }
            token = _metrics.set(metrics)
            started = time.perf_counter()
            status = "error"
            try:
                result = await method(self, *args, **kwargs)
                status = "success" if result is not None else "unavailable"
                if result is None and metrics["fallback_reason"] is None:
                    metrics["fallback_reason"] = "empty_or_invalid_response"
                return result
            except BaseException as exc:
                status = "cancelled" if type(exc).__name__ == "CancelledError" else "error"
                metrics["fallback_reason"] = metrics["fallback_reason"] or type(exc).__name__
                raise
            finally:
                event(
                    "llm_request",
                    operation=operation,
                    provider=getattr(self, "provider_name", type(self).__name__),
                    model=self.model,
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                    status=status,
                    **metrics,
                )
                _metrics.reset(token)

        return wrapped

    return decorate


def discord_context(feature: str):
    """Bind IDs from command contexts, messages or interactions for an entire callback."""

    def decorate(method):
        @wraps(method)
        async def wrapped(self, *args, **kwargs):
            source = next(
                (
                    arg
                    for arg in (*args, *kwargs.values())
                    if hasattr(arg, "guild") and hasattr(arg, "channel")
                ),
                None,
            )
            guild = getattr(source, "guild", None)
            channel = getattr(source, "channel", None)
            feature_name = feature
            if feature == "social_games" and args:
                game = self.sessions.get(args[0])
                feature_name = game.game_type if game is not None else feature
            if feature == "fun" and getattr(source, "command", None) is not None:
                feature_name = source.command.qualified_name
            actor = getattr(source, "author", None) or getattr(source, "user", None)
            user_id = getattr(actor, "id", None) if not getattr(actor, "bot", False) else None
            if feature == "social_games":
                user_id = kwargs.get("user_id", args[1] if len(args) > 1 else None)
            with model_context(
                feature_name,
                getattr(guild, "id", None),
                getattr(channel, "id", None),
                user_id,
            ):
                return await method(self, *args, **kwargs)

        return wrapped

    return decorate
