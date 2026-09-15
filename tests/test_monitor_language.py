"""Regression tests for monitored-channel language gating."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from weakref import WeakValueDictionary

from bot.cogs.monitor import ENGLISH_NUDGES, MonitorCog


def test_english_slang_is_not_sent_for_verification() -> None:
    assert MonitorCog._detect_lang("Control ur daughter") == "en"
    assert MonitorCog._detect_lang("pls tell her im busy") == "en"


def test_clear_non_english_text_is_selected_for_verification() -> None:
    assert MonitorCog._detect_lang("तुम कैसे हो") == "non-en"
    assert MonitorCog._detect_lang("kya haal hai bhai") == "hi-latin"


def test_language_response_requires_exact_non_english_label() -> None:
    assert MonitorCog._is_confirmed_non_english("NON_ENGLISH")
    assert MonitorCog._is_confirmed_non_english(" non_english ")
    assert not MonitorCog._is_confirmed_non_english("ENGLISH")
    assert not MonitorCog._is_confirmed_non_english("TRANSLATION: How are you?")


def test_nudge_variations_are_unique() -> None:
    assert len(ENGLISH_NUDGES) >= 6
    assert len(ENGLISH_NUDGES) == len(set(ENGLISH_NUDGES))

    cog = object.__new__(MonitorCog)
    cog._nudge_cycle = []
    one_cycle = [cog._playful_english_nudge() for _ in ENGLISH_NUDGES]
    assert set(one_cycle) == set(ENGLISH_NUDGES)


def test_memory_warning_counter_reaches_three_and_resets() -> None:
    async def scenario() -> None:
        cog = object.__new__(MonitorCog)
        cog.bot = SimpleNamespace(redis=None)
        cog._warning_counts = {}

        assert await cog._increment_warning(10, 20) == 1
        assert await cog._increment_warning(10, 20) == 2
        assert await cog._increment_warning(10, 20) == 3
        assert await cog._increment_warning(10, 20) == 3

        await cog._clear_warnings(10, 20)
        assert await cog._increment_warning(10, 20) == 1

    asyncio.run(scenario())


def test_simultaneous_messages_create_only_one_warning() -> None:
    async def scenario() -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        replies: list[str] = []

        class FakeLLM:
            def __init__(self) -> None:
                self.calls = 0

            async def generate(self, *_args, **_kwargs):
                self.calls += 1
                started.set()
                await release.wait()
                return SimpleNamespace(text="NON_ENGLISH")

        async def reply(content: str, **_kwargs) -> None:
            replies.append(content)

        llm = FakeLLM()
        cog = object.__new__(MonitorCog)
        cog.bot = SimpleNamespace(redis=None, build_llm_provider=lambda: llm)
        cog._last_seen = {}
        cog._decision_locks = WeakValueDictionary()
        cog._warning_counts = {}
        cog._nudge_cycle = []
        message = SimpleNamespace(
            guild=SimpleNamespace(id=10),
            author=SimpleNamespace(id=20),
            reply=reply,
        )

        async def process() -> None:
            async with cog._decision_lock(10, 20):
                await cog._process_non_english_candidate(message, "तुम कैसे हो")

        first = asyncio.create_task(process())
        await started.wait()
        second = asyncio.create_task(process())
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(first, second)

        assert llm.calls == 1
        assert len(replies) == 1
        assert cog._warning_counts[(10, 20)][0] == 1

    asyncio.run(scenario())
