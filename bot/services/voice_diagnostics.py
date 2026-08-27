"""Thread-safe diagnostics for the Discord <-> Gemini Live voice bridge."""

from __future__ import annotations

from collections import Counter
from threading import Lock
from typing import Any


class VoiceDiagnostics:
    """Counters shared safely by Discord audio threads and the asyncio loop."""

    def __init__(self) -> None:
        self._counts: Counter[str] = Counter()
        self._lock = Lock()

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counts[name] += amount

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)

    def format_snapshot(self, **metadata: Any) -> str:
        values = self.snapshot()
        counter_text = ", ".join(
            f"{name}={values.get(name, 0)}"
            for name in (
                "rtp_packets",
                "dave_success",
                "dave_failures",
                "opus_success",
                "opus_failures",
                "pcm_frames",
                "speech_frames",
                "gemini_input_chunks",
                "gemini_output_chunks",
                "playback_frames",
                "interruptions",
                "reconnects",
            )
        )
        metadata_text = " ".join(f"{key}={value}" for key, value in metadata.items())
        return f"{metadata_text}\n{counter_text}".strip()
