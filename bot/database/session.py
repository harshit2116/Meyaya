"""Async database session utilities."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from bot.database.urls import postgres_url

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def build_async_engine(database_url: str) -> AsyncEngine:
    """Create an async SQLAlchemy engine."""

    url, connect_args = postgres_url(database_url, asynchronous=True)
    return create_async_engine(
        url, pool_pre_ping=True, pool_size=2, max_overflow=1, connect_args=connect_args
    )


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory."""

    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def session_scope(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    """Yield a managed database session."""

    async with factory() as session:
        yield session
