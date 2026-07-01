"""Application entry point for Meyaya."""

from __future__ import annotations

import asyncio
from typing import NoReturn

from bot.app import create_bot


async def main() -> None:
    """Run the Discord bot."""

    bot = create_bot()
    async with bot:
        await bot.start(bot.settings.discord_token)


def run() -> NoReturn:
    """Execute the async entry point."""

    asyncio.run(main())
    raise SystemExit(0)


if __name__ == "__main__":
    run()
