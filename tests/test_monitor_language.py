"""Regression tests for monitored-channel language gating."""

from __future__ import annotations

from bot.cogs.monitor import ENGLISH_NUDGES, MonitorCog


def test_english_slang_is_not_sent_for_translation() -> None:
    assert MonitorCog._detect_lang("Control ur daughter") == "en"
    assert MonitorCog._detect_lang("pls tell her im busy") == "en"


def test_clear_non_english_text_is_selected_for_verification() -> None:
    assert MonitorCog._detect_lang("तुम कैसे हो") == "non-en"
    assert MonitorCog._detect_lang("kya haal hai bhai") == "hi-latin"


def test_translation_response_requires_explicit_non_english_label() -> None:
    assert MonitorCog._extract_translation("NO_TRANSLATION") is None
    assert MonitorCog._extract_translation("Control your daughter.") is None
    assert MonitorCog._extract_translation("TRANSLATION: How are you?") == "How are you?"


def test_nudge_variations_are_unique() -> None:
    assert len(ENGLISH_NUDGES) >= 6
    assert len(ENGLISH_NUDGES) == len(set(ENGLISH_NUDGES))

    cog = object.__new__(MonitorCog)
    cog._nudge_cycle = []
    one_cycle = [cog._playful_english_nudge() for _ in ENGLISH_NUDGES]
    assert set(one_cycle) == set(ENGLISH_NUDGES)
