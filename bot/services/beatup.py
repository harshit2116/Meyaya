"""High-quality face-tracked anime beatup looping GIF renderer."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from functools import lru_cache
import json
import logging
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any

from PIL import Image

from bot.logging.telemetry import event
from bot.services.disco_party import DiscoBusyError, DiscoDancer
from bot.services.gemini_tts import resolve_ffmpeg_executable
from bot.services.solosamba import _read_exact, render_face_sticker
from bot.utils.image_work import animation_work

logger = logging.getLogger(__name__)

BEATUP_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "beatup"
RENDER_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class BeatupTemplate:
    """Metadata for one face-tracked beatup looping GIF template."""

    key: str
    label: str
    verb: str
    min_cast: int = 2
    max_cast: int = 2


BEATUP_TEMPLATES: dict[str, BeatupTemplate] = {
    "invincible": BeatupTemplate(
        key="invincible",
        label="Invincible Beatdown",
        verb="folded",
        min_cast=2,
        max_cast=2,
    ),
}
DEFAULT_BEATUP_STYLE = "invincible"


@lru_cache(maxsize=8)
def _load_beatup_tracks(tracks_path_str: str) -> dict[str, Any] | None:
    path = Path(tracks_path_str)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("faces"), list):
        return None
    return data


def _render_beatup_gif_sync(
    base_video_path: Path,
    tracks_path: Path,
    dancers: list[DiscoDancer],
    ffmpeg_bin: str,
) -> bytes | None:
    """Decode base clip, paste face-tracked PFP stickers, and encode a 2-pass high-quality GIF."""
    tracks = _load_beatup_tracks(str(tracks_path))
    if tracks is None or not base_video_path.exists():
        return None

    width = int(tracks.get("width", 640))
    height = int(tracks.get("height", 360))
    fps = int(tracks.get("fps", 18))
    faces_by_frame: list[list[list[int]]] = tracks["faces"]
    total_frames = len(faces_by_frame)
    frame_bytes_len = width * height * 3

    stickers: dict[int, Image.Image] = {}
    for slot_idx, dancer in enumerate(dancers):
        stickers[slot_idx] = render_face_sticker(dancer, slot_idx)

    sprite_cache: dict[tuple[int, int, int], Image.Image] = {}

    def _get_sprite(slot: int, radius: int, angle_deg: int) -> Image.Image:
        diam = max(24, min(220, (radius * 2) & ~1))
        # Quantize angle to 2-degree buckets to reuse rotated sprites cleanly.
        ang_q = int(round(angle_deg / 2.0) * 2)
        key = (slot, diam, ang_q)
        cached = sprite_cache.get(key)
        if cached is None:
            spr = stickers[slot].resize((diam, diam), Image.Resampling.LANCZOS)
            if ang_q != 0:
                spr = spr.rotate(ang_q, resample=Image.Resampling.BILINEAR, expand=True)
            sprite_cache[key] = spr
            cached = spr
        return cached

    with tempfile.TemporaryDirectory(prefix="meyaya_beatup_") as tmpdir:
        out_path = Path(tmpdir) / "meyaya-beatup.gif"
        dec_err = Path(tmpdir) / "dec.err"
        enc_err = Path(tmpdir) / "enc.err"

        dec_cmd = [
            ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(base_video_path),
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "pipe:1",
        ]
        # 2-pass palettegen + sierra2_4a dithering inside one filtergraph for razor-sharp looping GIFs!
        gif_filter = (
            "split[s0][s1];"
            "[s0]palettegen=max_colors=256:stats_mode=diff[p];"
            "[s1][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle"
        )
        enc_cmd = [
            ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "rawvideo",
            "-vcodec",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{width}x{height}",
            "-r",
            str(fps),
            "-i",
            "pipe:0",
            "-vf",
            gif_filter,
            "-loop",
            "0",
            str(out_path),
        ]

        with dec_err.open("wb") as dec_err_f, enc_err.open("wb") as enc_err_f:
            dec_proc = subprocess.Popen(dec_cmd, stdout=subprocess.PIPE, stderr=dec_err_f)
            enc_proc = subprocess.Popen(enc_cmd, stdin=subprocess.PIPE, stderr=enc_err_f)
            assert dec_proc.stdout is not None
            assert enc_proc.stdin is not None
            try:
                for frame_idx in range(total_frames):
                    raw = _read_exact(dec_proc.stdout, frame_bytes_len)
                    if len(raw) < frame_bytes_len:
                        break
                    frame = Image.frombytes("RGB", (width, height), raw)
                    for item in faces_by_frame[frame_idx]:
                        cid = item[0]
                        if cid not in stickers:
                            continue
                        cx, cy, radius = item[1], item[2], item[3]
                        angle = item[4] if len(item) > 4 else 0
                        spr = _get_sprite(cid, radius, angle)
                        frame.paste(spr, (cx - spr.width // 2, cy - spr.height // 2), spr)
                    enc_proc.stdin.write(frame.tobytes())

                enc_proc.stdin.close()
                dec_proc.stdout.close()
                dec_proc.wait(timeout=10)
                enc_proc.wait(timeout=20)
            except Exception:
                for proc in (dec_proc, enc_proc):
                    with suppress(OSError):
                        proc.kill()
                    with suppress(OSError, subprocess.TimeoutExpired):
                        proc.wait(timeout=2)
                raise

        if enc_proc.returncode == 0 and out_path.exists():
            data = out_path.read_bytes()
            if data:
                return data
        logger.warning(
            "Beatup GIF ffmpeg failed dec_rc=%s enc_rc=%s",
            dec_proc.returncode,
            enc_proc.returncode,
        )
    return None


class BeatupRenderer:
    """Render face-tracked looping beatup GIFs with bounded concurrency."""

    def __init__(
        self,
        *,
        assets_root: Path = BEATUP_ASSETS_DIR,
        ffmpeg_executable: str = "ffmpeg",
    ) -> None:
        self.assets_root = assets_root
        self.ffmpeg_executable = ffmpeg_executable
        self._semaphore = asyncio.Semaphore(1)

    def template_paths(self, style: str) -> tuple[Path, Path]:
        clean = style if style in BEATUP_TEMPLATES else DEFAULT_BEATUP_STYLE
        folder = self.assets_root / clean
        return folder / "base.mp4", folder / "tracks.json"

    def is_template_ready(self, style: str) -> bool:
        base_path, tracks_path = self.template_paths(style)
        return base_path.exists() and tracks_path.exists()

    async def render(
        self,
        dancers: Sequence[DiscoDancer],
        *,
        style: str = DEFAULT_BEATUP_STYLE,
        max_bytes: int = 9 * 1024 * 1024,
    ) -> bytes | None:
        """Render a high-quality looping beatup GIF for the requested template style."""
        clean_style = style if style in BEATUP_TEMPLATES else DEFAULT_BEATUP_STYLE
        base_path, tracks_path = self.template_paths(clean_style)
        if len(dancers) < 2 or not base_path.exists() or not tracks_path.exists():
            return None
        if self._semaphore.locked():
            raise DiscoBusyError(
                "Another beatup GIF is rendering right now - try again in a few seconds!"
            )

        ffmpeg_bin = resolve_ffmpeg_executable(self.ffmpeg_executable)
        async with self._semaphore:
            started = time.monotonic()
            try:
                gif_bytes = await asyncio.wait_for(
                    animation_work(
                        _render_beatup_gif_sync,
                        base_path,
                        tracks_path,
                        list(dancers),
                        ffmpeg_bin,
                    ),
                    timeout=RENDER_TIMEOUT_SECONDS,
                )
            except (TimeoutError, Exception) as exc:
                logger.warning("Beatup GIF render unavailable (%s)", type(exc).__name__)
                return None

            if gif_bytes is None or len(gif_bytes) > max_bytes:
                return None
            event(
                "beatup_gif_rendered",
                style=clean_style,
                cast=len(dancers),
                bytes=len(gif_bytes),
                render_ms=round((time.monotonic() - started) * 1000, 1),
            )
            return gif_bytes
