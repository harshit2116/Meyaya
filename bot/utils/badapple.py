"""Bounded, versioned Bad Apple frame files; no bot or external-service imports."""

from __future__ import annotations

import gzip
import json
import math
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from PIL.Image import Image

MAX_CONTENT = 2000
MAX_ART = 1800  # Reserve room for progress, cancellation instructions and code fences.
MAX_FRAMES = 7200
MAX_CHARACTERS = 4_000_000
MAX_CACHE_BYTES = 16_000_000
DEFAULT_CACHE = Path("artifacts/badapple/frames.jsonl.gz")


class MediaError(ValueError):
    """Invalid or unavailable local animation, safe to explain to the developer."""


def validate_dimensions(width: int, height: int) -> None:
    if type(width) is not int or type(height) is not int or min(width, height) < 1:
        raise MediaError("Width and height must be positive integers.")
    if width * height + height - 1 > MAX_ART:
        raise MediaError(f"Frame dimensions exceed the {MAX_ART}-character art budget.")


def validate_frame(frame: str, width: int, height: int) -> None:
    if not isinstance(frame, str):
        raise MediaError("Each cached frame must be a string.")
    rows = frame.split("\n")
    if len(rows) != height or any(len(row) != width for row in rows):
        raise MediaError("Cached frame dimensions do not match the header.")
    if any(not "\u2800" <= char <= "\u28ff" for row in rows for char in row):
        raise MediaError("Frames may contain only Braille characters and row separators.")
    if len(frame) > MAX_ART:
        raise MediaError("Frame exceeds the Discord art budget.")


def render_content(frame: str, status: str) -> str:
    content = f"```\n{frame}\n```\n{status}"
    if len(content) > MAX_CONTENT:
        raise MediaError("Formatted frame exceeds Discord's 2000-character limit.")
    return content


def image_to_braille(image: Image, width: int, height: int, threshold: int = 128) -> str:
    """Fit a Pillow image to 2x4-dot cells (assumed character width/height = 0.5)."""
    from PIL import Image, ImageOps

    validate_dimensions(width, height)
    if type(threshold) is not int or not 0 <= threshold <= 255:
        raise MediaError("Threshold must be an integer from 0 to 255.")
    gray = ImageOps.pad(
        image.convert("L"),
        (width * 2, height * 4),
        method=Image.Resampling.LANCZOS,
        color=0,
    )
    pixels = gray.load()
    assert pixels is not None
    # Unicode dot numbering: left 1,2,3,7; right 4,5,6,8.
    dots = (
        (0, 0, 1),
        (0, 1, 2),
        (0, 2, 4),
        (1, 0, 8),
        (1, 1, 16),
        (1, 2, 32),
        (0, 3, 64),
        (1, 3, 128),
    )
    return "\n".join(
        "".join(
            chr(
                0x2800
                + sum(
                    bit
                    for dx, dy, bit in dots
                    if cast(int, pixels[x * 2 + dx, y * 4 + dy]) >= threshold
                )
            )
            for x in range(width)
        )
        for y in range(height)
    )


@dataclass(frozen=True)
class Animation:
    width: int
    height: int
    fps: float
    duration: float
    frames: tuple[str, ...]


def validate_metadata(header: object) -> tuple[int, int, float, float]:
    if not isinstance(header, dict) or header.get("version") != 1:
        raise MediaError("Unsupported frame cache header; preprocess the video again.")
    try:
        width, height = header["width"], header["height"]
        validate_dimensions(width, height)
        fps, duration = header["fps"], header["duration"]
        if any(type(value) not in (int, float) for value in (fps, duration)):
            raise MediaError("FPS and duration must be numbers.")
        if not math.isfinite(fps) or not 0.1 <= fps <= 6:
            raise MediaError("Sampling FPS must be between 0.1 and 6.")
        if not math.isfinite(duration) or not 0 < duration <= 3600:
            raise MediaError("Video duration must be positive and at most one hour.")
        expected = math.ceil(duration * fps)
        if expected > MAX_FRAMES or expected * (width * height + height - 1) > MAX_CHARACTERS:
            raise MediaError(
                "Animation exceeds the cache budget; lower resolution or sampling FPS."
            )
        return width, height, float(fps), float(duration)
    except (KeyError, TypeError) as exc:
        raise MediaError("Incomplete or malformed cache metadata.") from exc


def load_animation(path: Path) -> Animation:
    """Load once per playback, with limits on compressed/decompressed data and text.

    The retained art is at most 4M BMP characters (~8 MB in CPython). JSON is read
    one bounded line at a time, never as a second full copy of the dataset.
    """
    try:
        if path.stat().st_size > MAX_CACHE_BYTES:
            raise MediaError("Compressed frame cache is too large.")
        with gzip.open(path, "rb") as source:
            total_bytes = 0

            def read_record() -> object:
                nonlocal total_bytes
                line = source.readline(16_384)
                total_bytes += len(line)
                if total_bytes > MAX_CACHE_BYTES or not line.endswith(b"\n"):
                    raise MediaError("Truncated, oversized or empty frame cache.")
                return json.loads(line)

            width, height, fps, duration = validate_metadata(read_record())
            frames: list[str] = []
            characters = 0
            while True:
                record = read_record()
                if isinstance(record, dict):
                    if record != {"frames": len(frames)} or not frames:
                        raise MediaError("Invalid frame count or empty animation.")
                    if source.read(1):
                        raise MediaError("Unexpected data after the frame cache trailer.")
                    break
                if not isinstance(record, str):
                    raise MediaError("Each cached frame must be a string.")
                validate_frame(record, width, height)
                characters += len(record)
                if len(frames) >= MAX_FRAMES or characters > MAX_CHARACTERS:
                    raise MediaError("Frame cache exceeds the memory budget.")
                frames.append(record)
            if abs(len(frames) / fps - duration) > 1 / fps + 0.05:
                raise MediaError("Frame sequence does not cover the declared video duration.")
            return Animation(width, height, fps, duration, tuple(frames))
    except (OSError, EOFError, zlib.error, UnicodeError, json.JSONDecodeError) as exc:
        raise MediaError(
            "Frame cache is missing or corrupt; run the preprocessing script."
        ) from exc
