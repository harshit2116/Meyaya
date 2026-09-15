"""Application entry point for Meyaya."""

from __future__ import annotations

import asyncio
import signal
from contextlib import suppress
from typing import NoReturn

from bot.app import create_bot
from bot.runtime import restore_private_config


async def main() -> None:
    """Run the Discord bot."""

    restore_private_config()
    bot = create_bot()
    task = asyncio.current_task()
    loop = asyncio.get_running_loop()
    with suppress(NotImplementedError):
        loop.add_signal_handler(signal.SIGTERM, task.cancel)
    async with bot:
        await bot.start(bot.settings.discord_token)


def run() -> NoReturn:
    """Execute the async entry point."""

    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    raise SystemExit(0)


if __name__ == "__main__":
    run()
