"""One-shot voiced audio clips via Gemini TTS models."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Sequence
from io import BytesIO
import logging
import re
import time
import wave

import aiohttp

from bot.data.voices import canonical_voice_name
from bot.logging.telemetry import event
from bot.services.gemini_keys import GeminiKeyPool

logger = logging.getLogger(__name__)

GEMINI_TTS_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_TTS_CHARS = 280
TTS_TIMEOUT_SECONDS = 25.0
KEY_COOLDOWN_SECONDS = 60.0
_RATE_RE = re.compile(r"rate=(\d+)")


def _pcm_to_wav(pcm_bytes: bytes, *, sample_rate: int = 24000) -> bytes:
    buf = BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return buf.getvalue()


async def encode_discord_audio(
    wav_bytes: bytes,
    *,
    ffmpeg_executable: str = "ffmpeg",
) -> tuple[bytes, str]:
    """Encode WAV to MP3 for universal inline Discord Desktop+Mobile playback, falling back to WAV."""
    try:
        proc = await asyncio.create_subprocess_exec(
            ffmpeg_executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-vn",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            "-f",
            "mp3",
            "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        async with asyncio.timeout(6):
            stdout, _ = await proc.communicate(wav_bytes)
        if proc.returncode == 0 and stdout:
            return stdout, "meyaya-voice.mp3"
    except (OSError, TimeoutError):
        pass
    return wav_bytes, "meyaya-voice.wav"


class GeminiTTSService:
    """Generate short WAV voice clips across configured Gemini TTS fallback models."""

    def __init__(
        self,
        api_keys: tuple[str, ...],
        models: Sequence[str],
        http_session: aiohttp.ClientSession,
        *,
        default_voice: str = "Leda",
        key_pool: GeminiKeyPool | None = None,
    ) -> None:
        self.api_keys = tuple(dict.fromkeys(k.strip() for k in api_keys if k.strip()))
        self.models = tuple(
            dict.fromkeys(m.removeprefix("models/").strip() for m in models if m and m.strip())
        )
        self.http_session = http_session
        self.default_voice = canonical_voice_name(default_voice) or "Leda"
        self.key_pool = key_pool or GeminiKeyPool(self.api_keys)
        self._blocked_until: dict[tuple[str, int], float] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.api_keys and self.models)

    async def synthesize(
        self,
        text: str,
        *,
        voice_name: str | None = None,
        style: str | None = None,
        timeout_seconds: float = TTS_TIMEOUT_SECONDS,
        max_chars: int = MAX_TTS_CHARS,
    ) -> bytes | None:
        """Synthesize a short spoken WAV clip; returns None when unavailable."""

        limit = max(40, min(400, max_chars))
        clean = " ".join(text.split()).strip()[:limit]
        if not self.enabled or not clean:
            return None
        voice = canonical_voice_name(voice_name or "") or self.default_voice
        clean_style = " ".join((style or "").split()).strip()[:100]

        deadline = time.monotonic() + timeout_seconds
        for model in self.models:
            part: dict[str, object]
            if clean_style and model.startswith("gemini-3.8"):
                part = {"text": clean, "speechMetadata": {"style": clean_style}}
            elif clean_style:
                part = {
                    "text": (
                        "### DIRECTOR'S NOTES:\n"
                        f"{clean_style}\n\n"
                        "#### TRANSCRIPT:\n"
                        f"{clean}"
                    )
                }
            else:
                part = {"text": clean}
            payload = {
                "contents": [{"role": "user", "parts": [part]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}
                    },
                },
            }
            url = GEMINI_TTS_ENDPOINT.format(model=model)
            tried: set[int] = set()
            now = time.monotonic()
            while len(tried) < len(self.key_pool.slots):
                remaining = deadline - time.monotonic()
                if remaining <= 1.0:
                    return None
                eligible = [
                    i
                    for i in range(len(self.key_pool.slots))
                    if i not in tried and self._blocked_until.get((model, i), 0.0) <= now
                ]
                index = self.key_pool.acquire(eligible)
                if index is None:
                    break
                tried.add(index)
                key = self.key_pool.slots[index].value
                try:
                    async with asyncio.timeout(min(remaining, 15.0)):
                        async with self.http_session.post(
                            url,
                            json=payload,
                            headers={
                                "Content-Type": "application/json",
                                "x-goog-api-key": key,
                            },
                            timeout=aiohttp.ClientTimeout(total=min(remaining, 15.0)),
                        ) as response:
                            if response.status in {401, 403}:
                                self.key_pool.block(index)
                                continue
                            if response.status == 429:
                                self._blocked_until[(model, index)] = (
                                    time.monotonic() + KEY_COOLDOWN_SECONDS
                                )
                                continue
                            if response.status != 200:
                                event("gemini_tts_error", model=model, status=response.status)
                                if response.status in {500, 502, 503, 504}:
                                    continue
                                break
                            data = await response.json()
                            self.key_pool.success(index)
                except (aiohttp.ClientError, TimeoutError, ValueError):
                    continue
                finally:
                    self.key_pool.release(index)

                wav = self._extract_wav(data)
                if wav is not None:
                    event("gemini_tts_ok", model=model, bytes=len(wav))
                    return wav
        return None

    @staticmethod
    def _extract_wav(payload: object) -> bytes | None:
        if not isinstance(payload, dict):
            return None
        candidates = payload.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            return None
        content = candidates[0].get("content") if isinstance(candidates[0], dict) else None
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list):
            return None
        for part in parts:
            if not isinstance(part, dict):
                continue
            inline = part.get("inlineData") or part.get("inline_data")
            if not isinstance(inline, dict):
                continue
            raw_b64 = inline.get("data")
            mime = str(inline.get("mimeType") or inline.get("mime_type") or "").casefold()
            if not isinstance(raw_b64, str) or not raw_b64:
                continue
            try:
                audio = base64.b64decode(raw_b64)
            except ValueError:
                continue
            if not audio:
                continue
            if "wav" in mime or audio[:4] == b"RIFF":
                return audio
            rate_match = _RATE_RE.search(mime)
            sample_rate = int(rate_match.group(1)) if rate_match else 24000
            return _pcm_to_wav(audio, sample_rate=sample_rate)
        return None
