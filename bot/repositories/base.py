"""Repository base classes."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


class Repository:
    """Base repository carrying the database session."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
