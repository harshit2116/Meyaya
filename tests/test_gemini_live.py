"""Focused tests for Gemini Live transport recovery."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
import unittest

import bot.services.gemini_live as gemini_live


class _FakeSession:
    def __init__(self, *, fail_first_send: bool) -> None:
        self.fail_first_send = fail_first_send
        self.sent: list[dict] = []
        self.closed = asyncio.Event()

    async def send_realtime_input(self, **payload) -> None:
        if self.fail_first_send:
            self.fail_first_send = False
            raise ConnectionError("simulated ping timeout")
        self.sent.append(payload)

    async def receive(self):
        await self.closed.wait()
        if False:  # pragma: no cover - makes this an async generator
            yield None


class _FakeConnection:
    def __init__(self, session: _FakeSession) -> None:
        self.session = session

    async def __aenter__(self) -> _FakeSession:
        return self.session

    async def __aexit__(self, *_args) -> None:
        self.session.closed.set()


class _FakeLive:
    def __init__(self) -> None:
        self.sessions: list[_FakeSession] = []

    def connect(self, **_kwargs) -> _FakeConnection:
        session = _FakeSession(fail_first_send=not self.sessions)
        self.sessions.append(session)
        return _FakeConnection(session)


class _FakeClient:
    latest: "_FakeClient | None" = None

    def __init__(self, **_kwargs) -> None:
        self.live = _FakeLive()
        self.aio = SimpleNamespace(live=self.live)
        _FakeClient.latest = self


class _TurnSession:
    """Return one complete model turn from each receive() iterator."""

    def __init__(self) -> None:
        self.turns: asyncio.Queue[list[object]] = asyncio.Queue()
        self.receive_calls = 0

    async def receive(self):
        self.receive_calls += 1
        events = await self.turns.get()
        for event in events:
            yield event


def _audio_event(data: bytes) -> SimpleNamespace:
    return SimpleNamespace(
        usage_metadata=None,
        server_content=SimpleNamespace(
            interrupted=False,
            model_turn=SimpleNamespace(
                parts=[SimpleNamespace(inline_data=SimpleNamespace(data=data))]
            ),
        ),
    )


class GeminiLiveRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_completed_turn_keeps_session_for_next_turn(self) -> None:
        output: list[bytes] = []
        reconnect_reasons: list[str] = []

        async def capture(data: bytes) -> None:
            output.append(data)

        async def ignore(*_args) -> None:
            return None

        live = gemini_live.GeminiLiveSession(
            api_key="test-key",
            model="test-model",
            voice_name="test-voice",
            system_instruction="test",
            on_output_audio=capture,
            on_interrupted=ignore,
            on_input_audio_sent=ignore,
            on_reconnected=ignore,
        )
        session = _TurnSession()
        live._running = True
        live._session = session
        live._connected.set()

        async def unexpected_reconnect(_session, reason: str) -> None:
            reconnect_reasons.append(reason)

        live._reconnect = unexpected_reconnect  # type: ignore[method-assign]
        receiver = asyncio.create_task(live._receiver_loop())
        try:
            await session.turns.put([_audio_event(b"first-turn")])

            async def first_turn_finished() -> None:
                while len(output) < 1 or session.receive_calls < 2:
                    await asyncio.sleep(0)

            await asyncio.wait_for(first_turn_finished(), timeout=1)
            await session.turns.put([_audio_event(b"second-turn")])

            async def second_turn_finished() -> None:
                while len(output) < 2:
                    await asyncio.sleep(0)

            await asyncio.wait_for(second_turn_finished(), timeout=1)
            self.assertEqual(output, [b"first-turn", b"second-turn"])
            self.assertEqual(reconnect_reasons, [])
        finally:
            live._running = False
            receiver.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await receiver

    async def test_audio_send_reconnects_and_retries_once(self) -> None:
        original_genai = gemini_live.genai
        original_types = gemini_live.types
        gemini_live.genai = SimpleNamespace(Client=_FakeClient)
        gemini_live.types = SimpleNamespace(Blob=lambda **kwargs: SimpleNamespace(**kwargs))
        reconnects = 0

        async def on_reconnected() -> None:
            nonlocal reconnects
            reconnects += 1

        async def ignore(*_args) -> None:
            return None

        live = gemini_live.GeminiLiveSession(
            api_key="test-key",
            model="test-model",
            voice_name="test-voice",
            system_instruction="test",
            on_output_audio=ignore,
            on_interrupted=ignore,
            on_input_audio_sent=ignore,
            on_reconnected=on_reconnected,
        )
        try:
            await live.start()
            live.enqueue_audio_from_thread(b"\0" * 640)

            async def recovered() -> None:
                while True:
                    client = _FakeClient.latest
                    if (
                        client is not None
                        and len(client.live.sessions) == 2
                        and client.live.sessions[1].sent
                    ):
                        return
                    await asyncio.sleep(0)

            await asyncio.wait_for(recovered(), timeout=1)
            self.assertEqual(reconnects, 1)
            self.assertEqual(len(_FakeClient.latest.live.sessions), 2)
            self.assertIn("audio", _FakeClient.latest.live.sessions[1].sent[0])
        finally:
            await live.stop()
            gemini_live.genai = original_genai
            gemini_live.types = original_types


if __name__ == "__main__":
    unittest.main()
