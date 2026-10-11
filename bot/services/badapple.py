"""One bounded animation per bot process; sequential edits, no frame skipping."""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

import discord

from bot.utils.badapple import Animation, MediaError, load_animation, render_content

logger = logging.getLogger(__name__)


class PlaybackBusy(Exception):
    """The bot's single animation slot is already reserved."""


@dataclass(frozen=True)
class PlaybackResult:
    frames: int
    seconds: float
    target_fps: float

    @property
    def actual_fps(self) -> float:
        return self.frames / max(self.seconds, 0.001)


class BadApplePlayer:
    def __init__(self) -> None:
        self.task: asyncio.Task[object] | None = None
        self.owner_id: int | None = None
        self.channel_id: int | None = None
        self.stopping = False
        self.closed = False

    @asynccontextmanager
    async def reserve(self, owner_id: int, channel_id: int) -> AsyncIterator[None]:
        # No await between checking and reserving: concurrent invocations cannot queue.
        if self.task is not None or self.closed:
            raise PlaybackBusy
        self.task = asyncio.current_task()
        self.owner_id, self.channel_id = owner_id, channel_id
        try:
            yield
        finally:
            self.task = None
            self.owner_id = self.channel_id = None
            self.stopping = False

    async def load(self, path: Path) -> Animation:
        # Keep the slot reserved until the bounded file read really finishes, even
        # if cancelled. Cancelling to_thread alone cannot terminate its worker.
        pending = asyncio.create_task(asyncio.to_thread(load_animation, path))
        try:
            return await asyncio.shield(pending)
        except asyncio.CancelledError:
            try:
                await pending
            except MediaError:
                logger.debug("badapple_load_failed_after_cancellation")
            raise

    async def stop(self) -> None:
        task = self.task
        if task is not None and not self.stopping:
            self.stopping = True
            task.cancel()
        if task is not None:
            # Retrieve the child cancellation, without suppressing cancellation
            # of the stop command itself or issuing a second cancel to the player.
            await asyncio.shield(asyncio.gather(task, return_exceptions=True))

    async def close(self) -> None:
        self.closed = True
        await self.stop()

    async def play(
        self,
        message: discord.Message,
        animation: Animation,
        target_fps: float,
    ) -> PlaybackResult:
        if not math.isfinite(target_fps) or not 0.1 <= target_fps <= 6:
            raise ValueError("Playback FPS must be between 0.1 and 6.")
        # Never speed up a lower-sampled source accidentally.
        target_fps = min(target_fps, animation.fps)
        period = 1 / target_fps
        interval = period
        started = monotonic()
        last_slow_log = -math.inf
        displayed = 0
        frame = animation.frames[0]
        try:
            for frame in animation.frames:
                edit_started = monotonic()
                actual = (
                    f" · actual {displayed / max(edit_started - started, 0.001):.2f} FPS"
                    if displayed
                    else ""
                )
                # discord.py handles bucket waits and normal 429 retries. A leaked
                # HTTP/RateLimited exception is terminal; no additional retry loop.
                async with asyncio.timeout(120):
                    await message.edit(
                        content=render_content(
                            frame,
                            f"Bad Apple!! {displayed + 1}/{len(animation.frames)} · "
                            f"target {target_fps:g} FPS{actual} · /badapplestop",
                        ),
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                displayed += 1
                edit_finished = monotonic()
                edit_seconds = edit_finished - edit_started
                slow = edit_seconds >= max(1.0, interval * 2)
                if slow:
                    # API waits are included in edit latency. Back off toward one
                    # edit per second instead of resuming a fast burst after a wait.
                    # Never increase a caller's already slower requested pace.
                    interval = min(max(1.0, period), max(interval * 1.5, min(edit_seconds, 1.0)))
                    if edit_finished - last_slow_log >= 30:
                        logger.warning(
                            "badapple_slow_edit frame=%s edit_seconds=%.2f target_fps=%.2f "
                            "paced_fps=%.2f includes_api_waits=true channel=%s",
                            displayed,
                            edit_seconds,
                            target_fps,
                            1 / interval,
                            self.channel_id,
                        )
                        last_slow_log = edit_finished
                # Monotonic per-frame deadlines; slow edits stretch the timeline.
                # Never catch up in a burst or skip an overdue frame.
                await asyncio.sleep(
                    interval if slow else max(0, edit_started + interval - edit_finished)
                )
            result = PlaybackResult(displayed, monotonic() - started, target_fps)
            async with asyncio.timeout(120):
                await message.edit(
                    content=render_content(
                        frame,
                        f"Complete · {result.frames} frames · {result.seconds:.1f}s · "
                        f"target {target_fps:g} / actual {result.actual_fps:.2f} FPS",
                    ),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            return result
        except asyncio.CancelledError:
            try:
                async with asyncio.timeout(3):
                    await message.edit(
                        content=render_content(
                            frame,
                            f"Cancelled · {displayed}/{len(animation.frames)} frames displayed.",
                        ),
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
            except (discord.HTTPException, discord.RateLimited, TimeoutError):
                logger.info("badapple_cancel_status_unavailable channel=%s", self.channel_id)
            raise
