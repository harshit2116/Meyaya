"""Gemini Live API session wrapper for native audio streaming."""

from __future__ import annotations

import asyncio
import logging
import queue
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

try:
    from google import genai
    from google.genai import types
except Exception:  # pragma: no cover - optional dependency at runtime
    genai = None
    types = None

AudioCallback = Callable[[bytes], Awaitable[None]]
InterruptCallback = Callable[[], Awaitable[None]]
InputSentCallback = Callable[[int], Awaitable[None]]
ReconnectCallback = Callable[[], Awaitable[None]]
_QUEUE_EMPTY = object()


class GeminiLiveSession:
    """Persistent, self-healing Gemini Live audio connection."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        voice_name: str,
        system_instruction: str,
        on_output_audio: AudioCallback,
        on_interrupted: InterruptCallback,
        on_input_audio_sent: InputSentCallback,
        on_reconnected: ReconnectCallback,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.voice_name = voice_name
        self.system_instruction = system_instruction
        self.on_output_audio = on_output_audio
        self.on_interrupted = on_interrupted
        self.on_input_audio_sent = on_input_audio_sent
        self.on_reconnected = on_reconnected

        self._client = None
        self._conn_cm = None
        self._session = None
        self._running = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._receiver_task: asyncio.Task | None = None
        self._sender_task: asyncio.Task | None = None

        # Discord invokes the sink on its audio thread. A standard Queue is the
        # thread-safe boundary; an Event wakes the async sender without creating
        # a thread-pool job for every 20 ms audio frame.
        # ``None`` is an ordered audio-stream-end marker.
        self._input_audio_q: queue.Queue[bytes | None] = queue.Queue(maxsize=256)
        self._input_available = asyncio.Event()
        self._connected = asyncio.Event()
        self._reconnect_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()

        self._input_chunk_count = 0
        self._received_output_audio = False
        self._output_chunk_count = 0

    def _config(self) -> dict:
        return {
            "response_modalities": ["AUDIO"],
            "system_instruction": {"parts": [{"text": self.system_instruction}]},
            "speech_config": {
                "voice_config": {"prebuilt_voice_config": {"voice_name": self.voice_name}}
            },
            "realtime_input_config": {
                "automatic_activity_detection": {
                    "disabled": False,
                    "prefix_padding_ms": 80,
                    "silence_duration_ms": 550,
                }
            },
        }

    async def start(self) -> None:
        if self._running:
            return
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        if genai is None or types is None:
            raise RuntimeError(
                "google-genai SDK is not installed. Install dependency `google-genai` to use voice chat."
            )

        self._loop = asyncio.get_running_loop()
        self._client = genai.Client(api_key=self.api_key)
        self._running = True
        try:
            await self._open_connection()
        except Exception:
            self._running = False
            self._client = None
            raise

        self._receiver_task = asyncio.create_task(
            self._receiver_loop(), name="gemini-live-receiver"
        )
        self._sender_task = asyncio.create_task(self._sender_loop(), name="gemini-live-sender")

    async def _open_connection(self) -> None:
        assert self._client is not None
        logger.info(
            "Opening Gemini Live session model=%s voice=%s",
            self.model,
            self.voice_name,
        )
        conn_cm = self._client.aio.live.connect(model=self.model, config=self._config())
        session = await conn_cm.__aenter__()
        self._conn_cm = conn_cm
        self._session = session
        self._connected.set()
        logger.info("[GEMINI] session connected; setup complete")

    async def _close_connection(self) -> None:
        self._connected.clear()
        conn_cm = self._conn_cm
        self._conn_cm = None
        self._session = None
        if conn_cm is not None:
            try:
                await conn_cm.__aexit__(None, None, None)
            except asyncio.CancelledError:
                raise
            except Exception:
                # A failed socket commonly raises again while its context exits.
                logger.debug("Error closing failed Gemini socket", exc_info=True)

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._connected.set()
        self._input_available.set()

        for task in (self._sender_task, self._receiver_task):
            if task is not None:
                task.cancel()
        for task in (self._sender_task, self._receiver_task):
            if task is not None:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    logger.exception("Gemini task shutdown error")

        self._sender_task = None
        self._receiver_task = None
        await self._close_connection()
        self._client = None
        self._loop = None
        logger.info("Gemini Live session closed")

    def _wake_sender(self) -> None:
        loop = self._loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(self._input_available.set)

    def enqueue_audio_from_thread(self, pcm_16k_mono_s16le: bytes) -> None:
        """Accept one normalized PCM frame from Discord's receive thread."""

        if not self._running or not pcm_16k_mono_s16le:
            return
        try:
            self._input_audio_q.put_nowait(pcm_16k_mono_s16le)
        except queue.Full:
            # Prefer current speech over audio that is already several seconds old.
            try:
                self._input_audio_q.get_nowait()
            except queue.Empty:
                pass
            try:
                self._input_audio_q.put_nowait(pcm_16k_mono_s16le)
            except queue.Full:
                return
        self._wake_sender()

    async def signal_audio_end(self) -> None:
        """Queue an end marker after all previously queued PCM frames."""

        if not self._running:
            return
        try:
            self._input_audio_q.put_nowait(None)
        except queue.Full:
            try:
                self._input_audio_q.get_nowait()
                self._input_audio_q.put_nowait(None)
            except queue.Empty:
                return
        logger.info("[GEMINI] audio_stream_end queued after pending PCM")
        self._input_available.set()

    async def send_text(self, text: str) -> None:
        """Send a short realtime text prompt, used for voice output checks."""

        if not self._running:
            raise RuntimeError("Gemini Live session is not running")
        logger.info("Sending Gemini Live voice-check prompt")
        await self._send_with_recovery(text=text)

    def _next_queued_input(self) -> bytes | None | object:
        try:
            return self._input_audio_q.get_nowait()
        except queue.Empty:
            return _QUEUE_EMPTY

    async def _sender_loop(self) -> None:
        while self._running:
            chunk = self._next_queued_input()
            if chunk is _QUEUE_EMPTY:
                # Clear then re-check to close the race with a producer setting
                # the event immediately before this coroutine clears it.
                self._input_available.clear()
                chunk = self._next_queued_input()
                if chunk is _QUEUE_EMPTY:
                    await self._input_available.wait()
                    continue

            try:
                if chunk is None:
                    logger.info(
                        "[GEMINI] sending audio_stream_end after %s input chunks",
                        self._input_chunk_count,
                    )
                    await self._send_with_recovery(audio_stream_end=True)
                    continue

                assert isinstance(chunk, bytes)
                self._input_chunk_count += 1
                if self._input_chunk_count == 1:
                    logger.info("[GEMINI] first input audio chunk sent bytes=%s", len(chunk))
                elif self._input_chunk_count % 500 == 0:
                    logger.debug(
                        "[GEMINI] input chunk #%s sent bytes=%s",
                        self._input_chunk_count,
                        len(chunk),
                    )
                await self._send_with_recovery(
                    audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                )
                await self.on_input_audio_sent(len(chunk))
            except asyncio.CancelledError:
                raise
            except Exception:
                if self._running:
                    logger.exception("Gemini audio sender stopped unexpectedly")
                return

    async def _wait_for_session(self):
        while self._running:
            await self._connected.wait()
            if self._session is not None:
                return self._session
            self._connected.clear()
        raise asyncio.CancelledError

    async def _send_with_recovery(self, **payload) -> None:
        logged_failure = False
        while self._running:
            session = await self._wait_for_session()
            try:
                async with self._send_lock:
                    # The receiver may have replaced the socket while we waited.
                    if session is not self._session:
                        continue
                    await session.send_realtime_input(**payload)
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if not logged_failure:
                    logger.warning(
                        "[GEMINI] send failed (%s); reconnecting Live session",
                        exc,
                    )
                    logged_failure = True
                await self._reconnect(session, "send failure")
        raise asyncio.CancelledError

    async def _reconnect(self, failed_session, reason: str) -> None:
        async with self._reconnect_lock:
            if not self._running:
                return
            # Another task already recovered this exact failure.
            if self._session is not None and self._session is not failed_session:
                return

            logger.warning("[GEMINI] connection lost: %s", reason)
            await self._close_connection()

            attempt = 0
            while self._running:
                attempt += 1
                try:
                    await self._open_connection()
                    logger.info("[GEMINI] reconnected successfully on attempt %s", attempt)
                    await self.on_reconnected()
                    return
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    delay = min(2 ** (attempt - 1), 15)
                    logger.warning(
                        "[GEMINI] reconnect attempt %s failed (%s); retrying in %ss",
                        attempt,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)

    async def _receiver_loop(self) -> None:
        while self._running:
            session = await self._wait_for_session()
            try:
                async for event in session.receive():
                    if not self._running or session is not self._session:
                        break
                    await self._process_event(event)
                if self._running and session is self._session:
                    await self._reconnect(session, "server closed the receive stream")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self._running:
                    logger.warning("[GEMINI] receiver disconnected (%s); reconnecting", exc)
                    await self._reconnect(session, "receive failure")

    async def _process_event(self, event) -> None:
        try:
            server = getattr(event, "server_content", None)
            if server is None:
                return

            if getattr(server, "interrupted", False):
                await self.on_interrupted()

            model_turn = getattr(server, "model_turn", None)
            if model_turn is None:
                return

            parts = getattr(model_turn, "parts", []) or []
            for part in parts:
                inline = getattr(part, "inline_data", None)
                if inline is None or not getattr(inline, "data", None):
                    continue
                self._output_chunk_count += 1
                if not self._received_output_audio:
                    self._received_output_audio = True
                    logger.info("[GEMINI] first output audio chunk received")
                if self._output_chunk_count % 100 == 0:
                    logger.debug(
                        "[GEMINI] output audio chunk #%s received bytes=%s",
                        self._output_chunk_count,
                        len(inline.data),
                    )
                await self.on_output_audio(inline.data)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Error while processing Gemini Live event")
