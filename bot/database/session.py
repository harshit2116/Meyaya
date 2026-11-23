"""Async database session utilities."""

from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from time import monotonic
from collections.abc import AsyncIterator, Iterator
from typing import Any
from bot.database.urls import postgres_url
from sqlalchemy import event

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_dungeon_checkout = ContextVar("dungeon_checkout", default=False)
RECENT_CONNECTION_SECONDS = 10


@contextmanager
def dungeon_connection_reuse() -> Iterator[None]:
    """Reuse a just-verified connection during consecutive dungeon clicks."""
    token = _dungeon_checkout.set(True)
    try:
        yield
    finally:
        _dungeon_checkout.reset(token)


def _install_recent_dungeon_ping(engine: AsyncEngine) -> None:
    # asyncpg's health ping performs BEGIN + ping + ROLLBACK. Avoid those three
    # network round trips only for dungeon reads on a recently returned, still
    # open connection. Other commands and idle connections keep full pre-ping.
    returned: dict[int, float] = {}
    dialect: Any = engine.sync_engine.dialect
    original_ping = dialect.do_ping

    def ping(connection: Any) -> bool:
        recent = returned.get(id(connection))
        driver = getattr(connection, "driver_connection", None)
        if (_dungeon_checkout.get() and recent is not None
                and monotonic() - recent < RECENT_CONNECTION_SECONDS
                and driver is not None and not driver.is_closed()):
            return True
        return bool(original_ping(connection))

    dialect.do_ping = ping

    @event.listens_for(engine.sync_engine, "checkin")
    def remember(connection: Any, record: Any) -> None:
        if connection is not None:
            returned[id(connection)] = monotonic()

    @event.listens_for(engine.sync_engine, "close")
    @event.listens_for(engine.sync_engine, "invalidate")
    def forget(connection: Any, record: Any, *args: Any) -> None:
        returned.pop(id(connection), None)


def build_async_engine(database_url: str) -> AsyncEngine:
    """Create an async SQLAlchemy engine."""

    url, connect_args = postgres_url(database_url, asynchronous=True)
    engine = create_async_engine(
        url, pool_pre_ping=True, pool_size=2, max_overflow=1, connect_args=connect_args
    )
    _install_recent_dungeon_ping(engine)
    @event.listens_for(engine.sync_engine, "handle_error")
    def record_database_error(context: Any) -> None:
        # Covers failed statements and connection checkout, even if a service
        # catches the failure. Never record the SQL or driver exception text.
        from bot.logging.telemetry import event as emit
        emit("database_error", exception=type(context.original_exception).__name__)
    return engine


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory."""

    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def session_scope(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    """Yield a managed database session."""

    async with factory() as session:
        yield session
