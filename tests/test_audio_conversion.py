from __future__ import annotations

from bot.services.audio import (
    DISCORD_FRAME_BYTES,
    ResampleState,
    discord_pcm_48k_stereo_to_gemini_pcm_16k_mono,
    gemini_pcm_24k_mono_to_discord_pcm_48k_stereo,
)


def test_discord_to_gemini_pcm_conversion_produces_data() -> None:
    # 20ms silence frame for Discord PCM (48k stereo s16le)
    frame = b"\x00" * DISCORD_FRAME_BYTES
    out = discord_pcm_48k_stereo_to_gemini_pcm_16k_mono(frame, ResampleState())
    assert isinstance(out, (bytes, bytearray))
    assert len(out) > 0


def test_gemini_to_discord_pcm_conversion_produces_data() -> None:
    # 20ms silence at 24k mono s16le: 24000 * 0.02 * 1 * 2 = 960 bytes
    frame_24k = b"\x00" * 960
    out = gemini_pcm_24k_mono_to_discord_pcm_48k_stereo(frame_24k, ResampleState())
    assert isinstance(out, (bytes, bytearray))
    assert len(out) > 0
