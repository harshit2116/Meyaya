"""Bounded owner diagnostics, without exception messages or user content."""

from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path
import secrets
import time
import traceback


class ProviderUnavailable(Exception):
    """An AI call completed without a usable reply."""


def exception_evidence(error):
    """Keep bounded causal metadata, never exception messages or request bodies."""
    chain, seen = [], set()
    while isinstance(error, BaseException) and id(error) not in seen and len(chain) < 6:
        seen.add(id(error))
        item = {"exception": type(error).__name__}
        for key in ("status", "code"):
            value = getattr(error, key, None)
            if type(value) is int:
                item[key] = value
        frames = traceback.extract_tb(error.__traceback__)
        if frames:
            frame = frames[-1]
            item["location"] = f"{Path(frame.filename).name}:{frame.lineno} · {frame.name[:100]}"
        chain.append(item)
        error = (getattr(error, "original", None) or error.__cause__ or
                 (error.__context__ if not error.__suppress_context__ else None))
    return chain


def explain_error(record):
    """Explain recorded evidence; suggestions are not a claimed root cause."""
    chain = record.get("causes") or [{"exception": record.get("exception", "Unknown")}]
    root = chain[-1]
    kind, status, code = root.get("exception"), root.get("status"), root.get("code")
    if code == 10062:
        cause, action = "Discord interaction expired or is no longer available.", "Check interaction deferral and response timing."
    elif code == 10008:
        cause, action = "Discord could not find the message.", "Check whether the battle message was deleted before an edit."
    elif status == 403 or kind == "Forbidden":
        cause, action = "Discord or the provider denied access.", "Check permissions and credentials for the recorded operation."
    elif status == 429 or record.get("reason") == "http_429":
        cause, action = "The service rejected the request due to a rate or quota limit.", "Check quota and retry backoff."
    elif status in (500, 502, 503, 504) or record.get("reason") == "http_503":
        cause, action = "The upstream service reported a server failure.", "Check service availability and retry after backoff."
    elif kind in ("TimeoutError", "ServerTimeoutError", "ReadTimeout", "ConnectTimeout"):
        cause, action = "The operation exceeded its time limit.", "Check latency and availability at the recorded stage."
    elif kind == "ProviderUnavailable":
        cause, action = "The AI provider returned no usable reply.", "Inspect the recorded reason and matching AI request ID."
    else:
        cause = f"{kind} at the recorded stage; the exact cause was not retained."
        action = "Inspect the recorded source location and reproduce the failing operation."
    return {"cause": cause, "next_step": action, "root_exception": kind,
            "location": root.get("location")}


def with_diagnosis(record):
    return {**record, "diagnosis": explain_error(record)}


class HealthTelemetry:
    def __init__(self, capacity=500):
        self.capacity = capacity
        self.started_at = time.time()
        self.errors = OrderedDict()
        self.buckets = {}
        self.models = {}
        self.host = {}
        self.users = set()
        self.users_capped = False

    def count_error(self, category):
        if category not in {"gemini_429", "gemini_503", "discord_429", "db_errors"}:
            return
        minute = int(time.time() // 60)
        self.buckets = {key: value for key, value in self.buckets.items() if key > minute - 1440}
        bucket = self.buckets.setdefault(minute, {})
        bucket[category] = bucket.get(category, 0) + 1

    def counts(self):
        minute = int(time.time() // 60)
        return {category: sum(bucket.get(category, 0) for stamp, bucket in self.buckets.items()
                              if stamp > minute - 1440)
                for category in ("gemini_429", "gemini_503", "discord_429", "db_errors")}

    def record(self, payload):
        actor = payload.get("user_id")
        if isinstance(actor, int) and actor > 0:
            if len(self.users) < 10_000:
                self.users.add(actor)
            elif actor not in self.users:
                self.users_capped = True
        name = payload.get("event")
        if name == "llm_attempt_failed":
            category = {"http_429": "gemini_429", "http_503": "gemini_503"}.get(payload.get("reason"))
            if category:
                self.count_error(category)
        elif name in {"database_error", "discord_rate_limit"}:
            self.count_error("db_errors" if name == "database_error" else "discord_429")
        elif name in {"llm_request", "voice_connect", "voice_usage", "voice_reconnect"}:
            model = str(payload.get("model") or "unknown").removeprefix("models/")[:120]
            status = payload.get('status') or ('success' if name == 'voice_usage' else 'unavailable')
            self.models[model] = {"observed_at": time.time(), "status": status,
                                  "reason": payload.get("fallback_reason"),
                                  "latency_ms": payload.get("latency_ms")}
            while len(self.models) > 32:
                self.models.pop(next(iter(self.models)))

    def capture(self, error, *, command="unknown", guild_id=None, channel_id=None,
                invocation=None, stage=None, latency_ms=None, stages=None,
                provider=None, model=None, request_id=None, reason=None):
        previous = getattr(error, "_meyaya_error_id", None)
        if previous in self.errors:
            return previous
        error_id = "MY-" + secrets.token_hex(4).upper()
        while error_id in self.errors:
            error_id = "MY-" + secrets.token_hex(4).upper()
        # No exception str/repr, SQL, source lines, locals, or absolute paths:
        # provider and DB errors may embed credentials or user input.
        frames = [{"file": Path(frame.filename).name, "line": frame.lineno,
                   "function": frame.name[:100]}
                  for frame in traceback.extract_tb(error.__traceback__)[-12:]]
        record = {"error_id": error_id, "timestamp": datetime.now(UTC).isoformat(),
                  "command": str(command)[:80], "guild_id": guild_id, "channel_id": channel_id,
                  "invocation": invocation, "stage": stage or (frames[-1]["function"] if frames else "unknown"),
                  "exception": type(error).__name__, "latency_ms": latency_ms,
                  "stages": dict(stages or {}), "provider": provider, "model": model,
                  "request_id": request_id, "reason": reason,
                  "frames": frames, "causes": exception_evidence(error)}
        self.errors[error_id] = record
        while len(self.errors) > self.capacity:
            self.errors.popitem(last=False)
        try:
            error._meyaya_error_id = error_id
        except (AttributeError, TypeError):
            pass
        from bot.logging.telemetry import event
        event("command_error", **record)
        return error_id

    def search(self, error_id=""):
        if error_id:
            record = self.errors.get(error_id.upper())
            return [with_diagnosis(record)] if record else []
        return [with_diagnosis(record) for record in reversed(list(self.errors.values())[-30:])]


health = HealthTelemetry()


def find_retained_error(error_id):
    """Look up an exact ID in the existing bounded logs, never arbitrary files."""
    import json
    allowed = {'error_id', 'timestamp', 'command', 'guild_id', 'channel_id', 'invocation',
               'stage', 'exception', 'latency_ms', 'stages', 'provider', 'model', 'frames', 'request_id', 'reason', 'causes'}
    for suffix in ('', '.1', '.2', '.3'):
        try:
            with (Path('logs') / ('telemetry.jsonl' + suffix)).open(encoding='utf-8') as stream:
                remaining = 5_100_000
                while remaining > 0:
                    line = stream.readline(min(remaining, 65_536))
                    if not line:
                        break
                    remaining -= len(line.encode('utf-8'))
                    if error_id not in line:
                        continue
                    try:
                        item = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    if isinstance(item, dict) and item.get('event') == 'command_error' and item.get('error_id') == error_id:
                        return with_diagnosis({key: value for key, value in item.items() if key in allowed})
        except (OSError, UnicodeError):
            continue
    return None
