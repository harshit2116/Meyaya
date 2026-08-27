"""Audio conversion and playback helpers for Discord <-> Gemini Live streaming."""

from __future__ import annotations

try:
    import audioop  # Python <= 3.12
except Exception:  # pragma: no cover - fallback for newer Python versions
    import audioop_lts as audioop
import queue
import threading
from dataclasses import dataclass
from typing import Callable

import discord

DISCORD_SAMPLE_RATE = 48_000
DISCORD_CHANNELS = 2
DISCORD_SAMPLE_WIDTH = 2  # 16-bit
DISCORD_FRAME_MS = 20
DISCORD_FRAME_BYTES = int(
    DISCORD_SAMPLE_RATE * (DISCORD_FRAME_MS / 1000) * DISCORD_CHANNELS * DISCORD_SAMPLE_WIDTH
)

GEMINI_INPUT_RATE = 16_000
GEMINI_OUTPUT_RATE = 24_000


@dataclass
class ResampleState:
    to_16k: object | None = None
    from_24k: object | None = None


class PcmStreamAudioSource(discord.AudioSource):
    """Thread-safe PCM source that Discord voice playback can pull from.

    Discord calls `read()` from a worker thread, so this class avoids asyncio and uses
    a standard queue and lock-protected internal buffer.
    """

    def __init__(self, on_frame_consumed: Callable[[], None] | None = None) -> None:
        self._q: queue.Queue[bytes] = queue.Queue(maxsize=512)
        self._buffer = bytearray()
        self._closed = False
        self._lock = threading.Lock()
        self._on_frame_consumed = on_frame_consumed

    def is_opus(self) -> bool:
        return False

    def push(self, pcm_bytes: bytes) -> None:
        """Feed 48kHz stereo 16-bit PCM bytes."""

        if self._closed:
            return
        try:
            self._q.put_nowait(pcm_bytes)
        except queue.Full:
            # Drop oldest-ish behavior by taking one item and retrying.
            try:
                _ = self._q.get_nowait()
            except queue.Empty:
                pass
            try:
                self._q.put_nowait(pcm_bytes)
            except queue.Full:
                pass

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()
        while True:
            try:
                self._q.get_nowait()
            except queue.Empty:
                break

    def has_pending_audio(self) -> bool:
        """Return whether real model audio is buffered or queued for playback."""

        with self._lock:
            buffered = bool(self._buffer)
        return buffered or not self._q.empty()

    def close(self) -> None:
        self._closed = True
        self.clear()

    def read(self) -> bytes:
        if self._closed:
            return b""

        with self._lock:
            if len(self._buffer) >= DISCORD_FRAME_BYTES:
                frame = bytes(self._buffer[:DISCORD_FRAME_BYTES])
                del self._buffer[:DISCORD_FRAME_BYTES]
                self._notify_frame_consumed()
                return frame

        try:
            chunk = self._q.get(timeout=0.01)
        except queue.Empty:
            return b"\x00" * DISCORD_FRAME_BYTES

        with self._lock:
            self._buffer.extend(chunk)
            if len(self._buffer) >= DISCORD_FRAME_BYTES:
                frame = bytes(self._buffer[:DISCORD_FRAME_BYTES])
                del self._buffer[:DISCORD_FRAME_BYTES]
                self._notify_frame_consumed()
                return frame

        return b"\x00" * DISCORD_FRAME_BYTES

    def _notify_frame_consumed(self) -> None:
        if self._on_frame_consumed is not None:
            self._on_frame_consumed()


def discord_pcm_48k_stereo_to_gemini_pcm_16k_mono(
    pcm_48k_stereo: bytes,
    state: ResampleState,
) -> bytes:
    """Convert Discord receive PCM (48k stereo s16le) -> Gemini input PCM (16k mono s16le)."""

    mono_48k = audioop.tomono(pcm_48k_stereo, DISCORD_SAMPLE_WIDTH, 0.5, 0.5)
    resampled_16k, state.to_16k = audioop.ratecv(
        mono_48k,
        DISCORD_SAMPLE_WIDTH,
        1,
        DISCORD_SAMPLE_RATE,
        GEMINI_INPUT_RATE,
        state.to_16k,
    )
    return resampled_16k


def gemini_pcm_24k_mono_to_discord_pcm_48k_stereo(
    pcm_24k_mono: bytes,
    state: ResampleState,
) -> bytes:
    """Convert Gemini output PCM (24k mono s16le) -> Discord playback PCM (48k stereo s16le)."""

    resampled_48k, state.from_24k = audioop.ratecv(
        pcm_24k_mono,
        DISCORD_SAMPLE_WIDTH,
        1,
        GEMINI_OUTPUT_RATE,
        DISCORD_SAMPLE_RATE,
        state.from_24k,
    )
    stereo_48k = audioop.tostereo(resampled_48k, DISCORD_SAMPLE_WIDTH, 1.0, 1.0)
    return stereo_48k
