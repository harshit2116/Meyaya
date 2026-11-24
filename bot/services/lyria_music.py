"""Real-time ambient Discord VC background music powered by Lyria Realtime."""

from __future__ import annotations

import asyncio
from contextlib import suppress
import logging
from typing import Any

from bot.logging.telemetry import event
from bot.services.audio import PcmStreamAudioSource
from bot.services.gemini_keys import GeminiKeyPool

logger = logging.getLogger(__name__)

MAX_BGM_SECONDS = 180
MAX_PROMPT_CHARS = 180

genai: Any = None
types: Any = None


def _load_sdk() -> None:
    global genai, types
    if genai is not None and types is not None:
        return
    from google import genai as sdk
    from google.genai import types as sdk_types

    genai, types = sdk, sdk_types


class LyriaMusicSession:
    """Bounded streaming session pushing 48kHz stereo PCM into a Discord AudioSource."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        prompt: str,
        play_source: PcmStreamAudioSource,
        guild_id: int,
        key_pool: GeminiKeyPool | None = None,
        max_seconds: int = MAX_BGM_SECONDS,
        on_finished: Any = None,
    ) -> None:
        self.api_key = api_key
        self.model = model.removeprefix("models/").strip()
        self.prompt = " ".join(prompt.split()).strip()[:MAX_PROMPT_CHARS]
        self.play_source = play_source
        self.guild_id = guild_id
        self.key_pool = key_pool
        self.max_seconds = max_seconds
        self.on_finished = on_finished

        self._client: Any = None
        self._key_index: int | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active and self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self._active:
            return
        if not self.api_key and not (self.key_pool and self.key_pool.slots):
            raise RuntimeError("GEMINI_API_KEY is not configured")
        if genai is None or types is None:
            await asyncio.to_thread(_load_sdk)

        self._stop_event.clear()
        self._active = True
        self._task = asyncio.create_task(
            self._stream_loop(),
            name=f"lyria-bgm-{self.guild_id}",
        )

    async def stop(self) -> None:
        self._active = False
        self._stop_event.set()
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        self.play_source.clear()
        await self._close_client()

    def _acquire_key(self) -> str:
        if self.key_pool is not None and self.key_pool.slots:
            index = self.key_pool.acquire()
            if index is not None:
                self._key_index = index
                return self.key_pool.slots[index].value
        return self.api_key

    async def _close_client(self) -> None:
        client, self._client = self._client, None
        index, self._key_index = self._key_index, None
        if index is not None and self.key_pool is not None:
            self.key_pool.release(index)
        if client is None:
            return
        aclose = getattr(getattr(client, "aio", None), "aclose", None)
        if callable(aclose):
            with suppress(Exception):
                await aclose()
        close = getattr(client, "close", None)
        if callable(close):
            with suppress(Exception):
                close()

    async def _stream_loop(self) -> None:
        key = self._acquire_key()
        status = "unavailable"
        failure: str | None = "stream_not_started"
        try:
            self._client = genai.Client(
                api_key=key,
                http_options={"api_version": "v1alpha"},
            )
            async with asyncio.timeout(self.max_seconds):
                async with self._client.aio.live.music.connect(model=self.model) as session:
                    await session.set_weighted_prompts(
                        prompts=[types.WeightedPrompt(text=self.prompt, weight=1.0)]
                    )
                    await session.set_music_generation_config(
                        config=types.LiveMusicGenerationConfig(temperature=1.0)
                    )
                    await session.play()
                    event("lyria_bgm_started", guild_id=self.guild_id, model=self.model)
                    status, failure = "success", None
                    async for message in session.receive():
                        if self._stop_event.is_set():
                            break
                        server_content = getattr(message, "server_content", None)
                        chunks = getattr(server_content, "audio_chunks", None) or ()
                        for chunk in chunks:
                            data = getattr(chunk, "data", None)
                            if isinstance(data, (bytes, bytearray)) and data:
                                self.play_source.push(bytes(data))
                    with suppress(Exception):
                        await session.stop()
        except (asyncio.CancelledError, TimeoutError):
            pass
        except Exception as exc:
            if status != "success":
                status, failure = "error", type(exc).__name__
            event(
                "lyria_bgm_error",
                guild_id=self.guild_id,
                model=self.model,
                error=type(exc).__name__,
            )
            logger.warning("Lyria music stream stopped guild=%s error=%s", self.guild_id, type(exc).__name__)
        finally:
            self._active = False
            # No latency: stream length would skew the dashboard's model latency figures.
            event("llm_request", operation="music_stream", provider="lyria", model=self.model,
                  guild_id=self.guild_id, status=status, fallback_reason=failure)
            await self._close_client()
            if callable(self.on_finished):
                with suppress(Exception):
                    result = self.on_finished()
                    if asyncio.iscoroutine(result):
                        await result
