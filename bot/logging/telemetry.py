"""Task-local request metrics. Never log prompts, answers, credentials or evidence."""

from contextvars import ContextVar
from contextlib import contextmanager
from functools import wraps
import json
import logging
import time
from datetime import UTC, datetime
from uuid import uuid4

logger = logging.getLogger("meyaya.telemetry")
_context: ContextVar[dict | None] = ContextVar("llm_context", default=None)
_metrics: ContextVar[dict | None] = ContextVar("llm_metrics", default=None)


def event(name: str, **fields) -> None:
    logger.info(json.dumps({"timestamp": datetime.now(UTC).isoformat(),
                           "event": name, "feature": "unspecified", "guild_id": None,
                           "channel_id": None, **(_context.get() or {}), **fields}, default=str))


@contextmanager
def model_context(feature: str, guild_id: int | None, channel_id: int | None):
    token = _context.set({"feature": feature, "guild_id": guild_id, "channel_id": channel_id})
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
    event("llm_attempt_failed", request_id=(metrics or {}).get("request_id"), reason=reason, **fields)


def observe(operation: str):
    """Instrument adapter requests, including cancellations and empty results."""
    def decorate(method):
        @wraps(method)
        async def wrapped(self, *args, **kwargs):
            metrics = {
                "request_id": uuid4().hex, "input_tokens": None, "output_tokens": None,
                "total_tokens": None, "returned_model": None, "failed_requests": 0,
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
                event("llm_request", operation=operation,
                      provider=getattr(self, "provider_name", type(self).__name__),
                      model=self.model, latency_ms=round((time.perf_counter() - started) * 1000, 2),
                      status=status, **metrics)
                _metrics.reset(token)
        return wrapped
    return decorate


def discord_context(feature: str):
    """Bind IDs from command contexts, messages or interactions for an entire callback."""
    def decorate(method):
        @wraps(method)
        async def wrapped(self, *args, **kwargs):
            source = next((arg for arg in (*args, *kwargs.values())
                           if hasattr(arg, "guild") and hasattr(arg, "channel")), None)
            guild = getattr(source, "guild", None)
            channel = getattr(source, "channel", None)
            feature_name = feature
            if feature == "social_games" and args:
                game = self.sessions.get(args[0])
                feature_name = game.game_type if game is not None else feature
            if feature == "fun" and getattr(source, "command", None) is not None:
                feature_name = source.command.qualified_name
            with model_context(feature_name, getattr(guild, "id", None), getattr(channel, "id", None)):
                return await method(self, *args, **kwargs)
        return wrapped
    return decorate
