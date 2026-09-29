"""Last-mile redaction for diagnostics; never serialize settings or exceptions."""

import re
import math
from urllib.parse import urlsplit, unquote

PRIVATE_KEYS = {
    "authorization",
    "password",
    "token",
    "api_key",
    "database_url",
    "redis_url",
    "discord_token",
    "gemini_api_key",
    "headers",
    "request_body",
}


def secret_values(settings):
    values = []
    for name in (
        "discord_token",
        "gemini_api_key",
        "klipy_api_key",
        "database_url",
        "redis_url",
        "dashboard_token",
        "dashboard_api_token",
    ):
        value = getattr(settings, name, "")
        if value and len(value) >= 6:
            values.append(value)
            if "://" in value:
                try:
                    password = urlsplit(value).password
                    if password:
                        values.extend((password, unquote(password)))
                except ValueError:
                    pass
    return tuple(value for value in values if len(value) >= 6)


def sanitize(value, secrets=(), depth=0):
    if depth > 15:
        return None
    if isinstance(value, dict):
        return {
            str(key): (
                str(item)
                if str(key) in {"guild_id", "channel_id", "user_id", "owner_id"}
                and isinstance(item, int)
                else sanitize(item, secrets, depth + 1)
            )
            for key, item in value.items()
            if str(key).lower() not in PRIVATE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [sanitize(item, secrets, depth + 1) for item in value[:2000]]
    if isinstance(value, str):
        for secret in sorted(secrets, key=len, reverse=True):
            value = value.replace(secret, "[redacted]")
        value = re.sub(r'(?i)Bearer\s+[^\s"<>]+', "Bearer [redacted]", value)
        value = re.sub(r"\b\w+://[^\s/@]+:[^\s/@]+@[^\s]+", "[credential URL redacted]", value)
        value = re.sub(r"AIza[\w-]{20,}", "[redacted]", value)
        return value
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value if value is None or isinstance(value, (bool, int, float)) else None
