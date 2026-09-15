"""Translate provider Postgres URLs while preserving encoded credentials."""

import os
from sqlalchemy.engine import make_url


def postgres_url(value, *, asynchronous):
    url = make_url(value)
    if url.drivername.split("+")[0] not in {"postgres", "postgresql"}:
        raise ValueError("DATABASE_URL must use PostgreSQL")
    url = url.set(drivername="postgresql+asyncpg" if asynchronous else "postgresql+psycopg")
    mode = url.query.get("sslmode") or ("require" if os.getenv("DYNO") else None)
    if asynchronous:
        return url.difference_update_query(["sslmode"]), ({"ssl": mode} if mode else {})
    if mode:
        url = url.update_query_dict({"sslmode": mode})
    return url, {}
