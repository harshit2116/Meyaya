"""Async database session utilities."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from bot.database.urls import postgres_url
from sqlalchemy import event

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def build_async_engine(database_url: str) -> AsyncEngine:
    """Create an async SQLAlchemy engine."""

    url, connect_args = postgres_url(database_url, asynchronous=True)
    engine = create_async_engine(
        url, pool_pre_ping=True, pool_size=2, max_overflow=1, connect_args=connect_args
    )
    @event.listens_for(engine.sync_engine, "handle_error")
    def record_database_error(context):
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
