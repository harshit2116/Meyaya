import asyncio

from bot.config.settings import get_settings
from bot.database.base import Base
from bot.database.session import build_async_engine

# Import models so SQLAlchemy registers them
from bot.models import user, relationship, daily  # noqa: F401


async def main():
    engine = build_async_engine(get_settings().database_url)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await engine.dispose()
    print("Database initialized!")


asyncio.run(main())