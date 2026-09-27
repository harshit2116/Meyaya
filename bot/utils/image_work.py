"""Share one Pillow worker across commands to keep native image memory bounded."""

import asyncio
import logging
from time import monotonic
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from weakref import WeakKeyDictionary

from discord.ext import commands

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="meyaya-image")
_slots = WeakKeyDictionary()


class ImageBusy(commands.CommandError):
    def __init__(self):
        super().__init__("The card studio is busy. Please try again shortly.")


class BoundedImageGate:
    """Bound waiting callers as well as running jobs, before they fetch assets."""

    def __init__(self, capacity=4, *, concurrency=1):
        if not 1 <= concurrency <= capacity:
            raise ValueError("Concurrency must be between one and capacity")
        self.capacity = capacity
        self.pending = 0
        self.slot = asyncio.Semaphore(concurrency)

    async def acquire(self):
        if self.pending >= self.capacity:
            raise ImageBusy()
        self.pending += 1
        try:
            async with asyncio.timeout(10):
                await self.slot.acquire()
        except BaseException as error:
            self.pending -= 1
            if isinstance(error, TimeoutError):
                raise ImageBusy() from None
            raise

    def release(self):
        self.pending -= 1
        self.slot.release()

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, *args):
        self.release()


async def image_work(function, *args, **kwargs):
    loop = asyncio.get_running_loop()
    slot = _slots.setdefault(loop, BoundedImageGate())
    queued = monotonic()
    await slot.acquire()
    wait = monotonic() - queued
    if wait >= 0.5:
        logging.getLogger(__name__).info("image_queue function=%s wait_ms=%.0f", getattr(function, "__name__", "image"), wait * 1000)
    try:
        future = loop.run_in_executor(_executor, partial(function, *args, **kwargs))
    except BaseException:
        slot.release()
        raise
    # Cancellation cannot stop Pillow. Release only when the actual work finishes.
    future.add_done_callback(lambda _: slot.release())
    return await asyncio.shield(future)
