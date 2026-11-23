"""Translate provider Postgres URLs while preserving encoded credentials."""

from __future__ import annotations

import os
import ssl
from typing import Any

from sqlalchemy.engine import URL, make_url


def postgres_url(value: str | URL, *, asynchronous: bool) -> tuple[URL, dict[str, Any]]:
    url = make_url(value)
    if url.drivername.split("+")[0] not in {"postgres", "postgresql"}:
        raise ValueError("DATABASE_URL must use PostgreSQL")
    url = url.set(drivername="postgresql+asyncpg" if asynchronous else "postgresql+psycopg")
    raw_mode = url.query.get("sslmode")
    mode = (
        raw_mode[0] if isinstance(raw_mode, tuple) and raw_mode else (raw_mode if isinstance(raw_mode, str) else None)
    ) or ("require" if os.getenv("DYNO") else None)
    if asynchronous:
        # Neon supplies libpq options; SQLAlchemy otherwise forwards these as
        # unsupported keyword arguments to asyncpg.connect(). Keep the original
        # URL intact for psycopg/Alembic, which understands channel_binding.
        binding = url.query.get("channel_binding")
        args: dict[str, Any] = {"ssl": mode} if mode else {}
        if binding == "require":
            # asyncpg has no channel_binding switch. Require verified TLS
            # (certificate AND hostname), never silently fall back to plaintext.
            # This is transport verification, not a libpq channel-binding flag.
            args["ssl"] = ssl.create_default_context()
        return url.difference_update_query(["sslmode", "channel_binding"]), args
    if mode:
        url = url.update_query_dict({"sslmode": mode})
    return url, {}
