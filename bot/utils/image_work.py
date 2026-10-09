"""Bound image work while keeping long animations out of the card queue."""

import asyncio
import logging
from time import monotonic
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from weakref import WeakKeyDictionary

from discord.ext import commands
from bot.utils.command_timing import add_stage

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="meyaya-card")
_animation_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="meyaya-animation")
_slots = WeakKeyDictionary()
_animation_slots = WeakKeyDictionary()


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
    return await _image_work(_executor, _slots, 6, 2, function, args, kwargs)


async def animation_work(function, *args, **kwargs):
    """Serialize memory-heavy GIF jobs without holding up ordinary cards."""
    return await _image_work(_animation_executor, _animation_slots, 3, 1, function, args, kwargs)


async def _image_work(executor, slots, capacity, concurrency, function, args, kwargs):
    loop = asyncio.get_running_loop()
    slot = slots.setdefault(loop, BoundedImageGate(capacity, concurrency=concurrency))
    queued = monotonic()
    await slot.acquire()
    wait = monotonic() - queued
    add_stage('image_queue_ms', wait * 1000)
    if wait >= 0.5:
        logging.getLogger(__name__).info("image_queue function=%s wait_ms=%.0f", getattr(function, "__name__", "image"), wait * 1000)
    try:
        future = loop.run_in_executor(executor, partial(function, *args, **kwargs))
    except BaseException:
        slot.release()
        raise
    # Cancellation cannot stop Pillow. Release only when the actual work finishes.
    def finished(completed):
        slot.release()
        # The original caller may have been cancelled while Pillow was running.
        # Retrieve failures in that case too; awaiting callers still receive them.
        if not completed.cancelled():
            completed.exception()
    future.add_done_callback(finished)
    started = monotonic()
    try:
        return await asyncio.shield(future)
    finally:
        add_stage('render_ms', (monotonic() - started) * 1000)
