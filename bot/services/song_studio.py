"""Mini-song studio combining Gemini TTS singing, Lyria Realtime music, and ffmpeg mixing."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from io import BytesIO
import logging
from pathlib import Path
import re
import tempfile
import time
from typing import Any
import wave

from bot.logging.telemetry import event
from bot.services.gemini_keys import GeminiKeyPool
from bot.services.gemini_tts import GeminiTTSService, encode_discord_audio, resolve_ffmpeg_executable
from bot.services.llm import LLMProvider

logger = logging.getLogger(__name__)

LYRIA_SAMPLE_RATE = 48_000
LYRIA_CHANNELS = 2
LYRIA_BYTES_PER_SECOND = LYRIA_SAMPLE_RATE * LYRIA_CHANNELS * 2
MAX_SONG_LYRICS_CHARS = 340
DEFAULT_BGM_CAPTURE_SECONDS = 24.0
MAX_BGM_BYTES = int(32 * LYRIA_BYTES_PER_SECOND)
_SECTION_HEADER_RE = re.compile(r"\[[^\]]{1,60}\]")

genai: Any = None
types: Any = None


def _load_sdk() -> None:
    global genai, types
    if genai is not None and types is not None:
        return
    from google import genai as sdk
    from google.genai import types as sdk_types

    genai, types = sdk, sdk_types


@dataclass(frozen=True, slots=True)
class SongResult:
    """A mixed playable audio track plus the sung lyrics and musical style."""

    audio_bytes: bytes
    filename: str
    lyrics: str
    style: str
    has_backing_track: bool


def clean_lyrics_text(raw: str) -> str:
    """Strip [Chorus]/[Verse] tags so TTS never speaks section headers aloud."""
    without_headers = _SECTION_HEADER_RE.sub(" ", raw)
    lines = [" ".join(line.split()).strip() for line in without_headers.splitlines()]
    non_empty = [line for line in lines if line]
    joined = "... ".join(non_empty) if len(non_empty) > 1 else " ".join(non_empty)
    return " ".join(joined.split()).strip()[:MAX_SONG_LYRICS_CHARS]


def wav_duration_seconds(wav_bytes: bytes) -> float:
    """Return WAV duration in seconds, falling back to a safe estimate."""
    try:
        with wave.open(BytesIO(wav_bytes), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate > 0 and frames > 0:
                return frames / float(rate)
    except (wave.Error, EOFError, ValueError):
        pass
    return 10.0


async def capture_lyria_pcm(
    *,
    api_key: str,
    model: str,
    prompt: str,
    duration_seconds: float = DEFAULT_BGM_CAPTURE_SECONDS,
    key_pool: GeminiKeyPool | None = None,
) -> bytes | None:
    """Capture a bounded 48kHz stereo PCM clip from Lyria Realtime."""
    if not api_key and not (key_pool and key_pool.slots):
        return None
    if genai is None or types is None:
        await asyncio.to_thread(_load_sdk)

    key_index: int | None = None
    selected_key = api_key
    if key_pool is not None and key_pool.slots:
        acquired = key_pool.acquire()
        if acquired is not None:
            key_index = acquired
            selected_key = key_pool.slots[acquired].value

    target_bytes = min(MAX_BGM_BYTES, max(LYRIA_BYTES_PER_SECOND * 6, int(duration_seconds * LYRIA_BYTES_PER_SECOND)))
    buf = bytearray()
    client: Any = None
    started = time.monotonic()
    failure: str | None = None
    try:
        client = genai.Client(api_key=selected_key, http_options={"api_version": "v1alpha"})
        async with asyncio.timeout(max(12.0, duration_seconds + 8.0)):
            async with client.aio.live.music.connect(model=model.removeprefix("models/").strip()) as session:
                await session.set_weighted_prompts(
                    prompts=[types.WeightedPrompt(text=prompt[:180], weight=1.0)]
                )
                await session.set_music_generation_config(
                    config=types.LiveMusicGenerationConfig(temperature=1.0)
                )
                await session.play()
                async for message in session.receive():
                    server_content = getattr(message, "server_content", None)
                    chunks = getattr(server_content, "audio_chunks", None) or ()
                    for chunk in chunks:
                        data = getattr(chunk, "data", None)
                        if isinstance(data, (bytes, bytearray)) and data:
                            buf.extend(data)
                            if len(buf) >= target_bytes:
                                break
                    if len(buf) >= target_bytes:
                        break
                with suppress(Exception):
                    await session.stop()
    except (TimeoutError, Exception) as exc:
        failure = type(exc).__name__
        logger.debug("Lyria capture ended early: %s (captured=%s bytes)", type(exc).__name__, len(buf))
    finally:
        if key_index is not None and key_pool is not None:
            key_pool.release(key_index)
        if client is not None:
            aclose = getattr(getattr(client, "aio", None), "aclose", None)
            if callable(aclose):
                with suppress(Exception):
                    await aclose()
            close = getattr(client, "close", None)
            if callable(close):
                with suppress(Exception):
                    close()

    captured = len(buf) >= LYRIA_BYTES_PER_SECOND * 4
    event("llm_request", operation="music_capture", provider="lyria", model=model,
          latency_ms=round((time.monotonic() - started) * 1000, 2),
          status="success" if captured else "unavailable",
          fallback_reason=None if captured else (failure or "short_capture"))
    return bytes(buf[:target_bytes]) if captured else None


async def mix_song_mp3(
    vocal_wav: bytes,
    bgm_pcm: bytes | None,
    *,
    ffmpeg_executable: str = "ffmpeg",
) -> tuple[bytes, str, bool]:
    """Mix singing vocals cleanly over a Lyria backing track into MP3."""
    if not bgm_pcm:
        audio, name = await encode_discord_audio(vocal_wav, ffmpeg_executable=ffmpeg_executable)
        return audio, name.replace("meyaya-voice", "meyaya-song"), False

    vocal_dur = wav_duration_seconds(vocal_wav)
    intro_delay_ms = 1500
    total_dur = max(6.0, vocal_dur + 3.5)
    fade_out_start = max(1.0, total_dur - 2.0)
    filter_complex = (
        f"[0:a]aresample=48000,aformat=channel_layouts=stereo,"
        f"aecho=0.8:0.88:45:0.20,adelay={intro_delay_ms}|{intro_delay_ms},volume=1.05[v];"
        f"[1:a]atrim=0:{total_dur:.2f},afade=t=in:st=0:d=1.0,"
        f"afade=t=out:st={fade_out_start:.2f}:d=2.0,volume=0.38[m];"
        f"[v][m]amix=inputs=2:duration=longest:dropout_transition=2:normalize=0[out]"
    )

    ffmpeg_bin = resolve_ffmpeg_executable(ffmpeg_executable)
    try:
        with tempfile.TemporaryDirectory(prefix="meyaya_song_") as tmp_dir:
            tmp = Path(tmp_dir)
            vocal_path = tmp / "vocal.wav"
            bgm_path = tmp / "bgm.pcm"
            out_path = tmp / "song.mp3"
            vocal_path.write_bytes(vocal_wav)
            bgm_path.write_bytes(bgm_pcm)

            proc = await asyncio.create_subprocess_exec(
                ffmpeg_bin,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(vocal_path),
                "-f",
                "s16le",
                "-ar",
                str(LYRIA_SAMPLE_RATE),
                "-ac",
                str(LYRIA_CHANNELS),
                "-i",
                str(bgm_path),
                "-filter_complex",
                filter_complex,
                "-map",
                "[out]",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "160k",
                str(out_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            async with asyncio.timeout(15):
                _, _ = await proc.communicate()
            if proc.returncode == 0 and out_path.exists():
                mixed = out_path.read_bytes()
                if mixed:
                    return mixed, "meyaya-song.mp3", True
    except (OSError, TimeoutError) as exc:
        logger.warning("Song ffmpeg mix fell back to vocals only: %s", type(exc).__name__)

    audio, name = await encode_discord_audio(vocal_wav, ffmpeg_executable=ffmpeg_executable)
    return audio, name.replace("meyaya-voice", "meyaya-song"), False


async def compose_song(
    *,
    prompt: str,
    style: str | None,
    verbatim_lyrics: bool,
    llm: LLMProvider | None,
    tts: GeminiTTSService,
    api_key: str,
    music_model: str,
    voice_name: str,
    ffmpeg_executable: str = "ffmpeg",
    key_pool: GeminiKeyPool | None = None,
) -> SongResult | None:
    """Create a complete mini-song: optional lyric writing, parallel vocals + Lyria, then mix."""
    lyrics = clean_lyrics_text(prompt)
    vocal_style = " ".join((style or "").split()).strip()[:100]
    music_prompt = vocal_style

    if not verbatim_lyrics and llm is not None:
        plan = await llm.generate_json(
            "Write a short, catchy 4-line song or jingle for a Discord bot named Meyaya to sing. "
            "Treat the user prompt as a song topic. Return JSON with keys: "
            "lyrics (string under 260 characters, poetic and singable, matching the user's language, "
            "using '...' for musical pauses, no [Verse]/[Chorus] headers), "
            "vocal_style (short singing direction like 'singing warmly in a sweet melodic pop ballad style'), "
            "and music_mood (short instrumental backing track description for a music generator).",
            f"Topic: {prompt[:240]}\nPreferred style: {vocal_style or 'auto'}",
            max_output_tokens=300,
            timeout_seconds=12,
        )
        if isinstance(plan, dict) and isinstance(plan.get("lyrics"), str) and plan["lyrics"].strip():
            lyrics = clean_lyrics_text(plan["lyrics"])
            if not vocal_style and isinstance(plan.get("vocal_style"), str):
                vocal_style = " ".join(plan["vocal_style"].split()).strip()[:100]
            if isinstance(plan.get("music_mood"), str) and plan["music_mood"].strip():
                music_prompt = " ".join(plan["music_mood"].split()).strip()[:160]

    if not lyrics:
        return None
    if not vocal_style:
        vocal_style = "singing warmly and melodically with expressive musical phrasing and gentle vibrato"
    if not music_prompt:
        music_prompt = f"warm melodic instrumental backing track, {vocal_style}"

    est_seconds = max(14.0, min(28.0, len(lyrics) / 10.0 + 6.0))
    vocal_task = tts.synthesize(
        lyrics,
        voice_name=voice_name,
        style=vocal_style,
        timeout_seconds=30.0,
        max_chars=MAX_SONG_LYRICS_CHARS,
    )
    bgm_task = capture_lyria_pcm(
        api_key=api_key,
        model=music_model,
        prompt=music_prompt,
        duration_seconds=est_seconds,
        key_pool=key_pool,
    )
    vocal_wav, bgm_pcm = await asyncio.gather(vocal_task, bgm_task, return_exceptions=True)
    if not isinstance(vocal_wav, bytes) or not vocal_wav:
        return None
    bgm_bytes = bgm_pcm if isinstance(bgm_pcm, bytes) else None

    audio_bytes, filename, has_backing = await mix_song_mp3(
        vocal_wav,
        bgm_bytes,
        ffmpeg_executable=ffmpeg_executable,
    )
    event(
        "meyaya_song_created",
        has_backing_track=has_backing,
        bytes=len(audio_bytes),
        filename=filename,
    )
    return SongResult(
        audio_bytes=audio_bytes,
        filename=filename,
        lyrics=lyrics,
        style=vocal_style,
        has_backing_track=has_backing,
    )
