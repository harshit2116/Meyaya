"""Solo Samba face-tracked video renderer starring the command invoker and Meyaya."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from contextlib import suppress
from functools import lru_cache
import json
import logging
import math
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any

from PIL import Image, ImageDraw, ImageOps

from bot.logging.telemetry import event
from bot.services.disco_party import (
    ASSETS_DIR as DISCO_ASSETS_DIR,
    BEAT_HZ,
    DiscoBusyError,
    DiscoDancer,
    _base_shadow_sprite,
    _decode_avatar,
    _extract_accent_color,
    _load_label_font,
    _load_meyaya_frames,
)
from bot.services.gemini_tts import resolve_ffmpeg_executable
from bot.utils.image_work import animation_work

logger = logging.getLogger(__name__)

SOLOSAMBA_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "solosamba"
DEFAULT_BASE_VIDEO_PATH = SOLOSAMBA_ASSETS_DIR / "base.mp4"
DEFAULT_TRACKS_PATH = SOLOSAMBA_ASSETS_DIR / "tracks.json"

MAX_CAST = 6
RENDER_TIMEOUT_SECONDS = 45.0

_STICKER_PALETTE: tuple[tuple[int, int, int], ...] = (
    (255, 84, 198),
    (42, 232, 255),
    (255, 206, 56),
    (176, 108, 255),
    (74, 248, 158),
    (255, 128, 72),
)


@lru_cache(maxsize=2)
def _load_tracks(tracks_path_str: str) -> dict[str, Any] | None:
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


def render_face_sticker(dancer: DiscoDancer, slot_index: int) -> Image.Image:
    """Build a crisp, tight circular PFP sticker that sits cleanly on a character's face."""
    size = 200
    avatar_size = 184
    pad = (size - avatar_size) // 2
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    avatar = _decode_avatar(dancer.avatar_bytes)
    accent = (
        _extract_accent_color(avatar, slot_index)
        if avatar is not None
        else _STICKER_PALETTE[slot_index % len(_STICKER_PALETTE)]
    )

    draw = ImageDraw.Draw(canvas)
    # Thin dark outline + neon accent ring + crisp inner white rim (keeps character hair/ears visible).
    draw.ellipse((0, 0, size - 1, size - 1), fill=(*accent, 255), outline=(18, 10, 30, 235), width=3)
    draw.ellipse(
        (pad - 3, pad - 3, pad + avatar_size + 3, pad + avatar_size + 3),
        fill=(255, 255, 255, 255),
    )

    if avatar is not None:
        fitted = ImageOps.fit(avatar, (avatar_size, avatar_size), method=Image.Resampling.LANCZOS)
    else:
        fitted = Image.new("RGBA", (avatar_size, avatar_size), (*accent, 255))
        fdraw = ImageDraw.Draw(fitted)
        initial = (dancer.display_name[:1] or "?").upper()
        font = _load_label_font(86)
        bbox = fdraw.textbbox((0, 0), initial, font=font)
        fdraw.text(
            (
                (avatar_size - int(bbox[2] - bbox[0])) // 2 - int(bbox[0]),
                (avatar_size - int(bbox[3] - bbox[1])) // 2 - int(bbox[1]),
            ),
            initial,
            font=font,
            fill=(255, 255, 255, 255),
        )

    mask_hi = Image.new("L", (avatar_size * 2, avatar_size * 2), 0)
    ImageDraw.Draw(mask_hi).ellipse((0, 0, avatar_size * 2 - 1, avatar_size * 2 - 1), fill=255)
    mask = mask_hi.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
    canvas.paste(fitted, (pad, pad), mask)
    return canvas


def _read_exact(stream: Any, size: int) -> bytes:
    buf = bytearray()
    while len(buf) < size:
        chunk = stream.read(size - len(buf))
        if not chunk:
            break
        buf.extend(chunk)
    return bytes(buf)


def _render_solosamba_sync(
    base_video_path: Path,
    tracks_path: Path,
    meyaya_assets_dir: Path,
    dancers: list[DiscoDancer],
    ffmpeg_bin: str,
) -> bytes | None:
    """Stream base video frames, paste face-tracked circular PFPs + Meyaya cameo, and re-encode MP4."""
    tracks = _load_tracks(str(tracks_path))
    if tracks is None or not base_video_path.exists():
        return None

    width = int(tracks.get("width", 854))
    height = int(tracks.get("height", 480))
    fps = int(tracks.get("fps", 24))
    faces_by_frame: list[list[list[int]]] = tracks["faces"]
    meyaya_map: dict[str, list[float]] = tracks.get("meyaya") or {}
    total_frames = len(faces_by_frame)
    frame_bytes_len = width * height * 3

    # Build tight circular face stickers only for populated slots (unassigned characters keep original faces).
    stickers: dict[int, Image.Image] = {}
    for slot_idx, dancer in enumerate(dancers[:MAX_CAST]):
        stickers[slot_idx] = render_face_sticker(dancer, slot_idx)

    meyaya_frames = _load_meyaya_frames(str(meyaya_assets_dir))
    base_shadow = _base_shadow_sprite()
    # Small per-render cache of resized stickers by (slot, diameter_bucket) to speed up 668 frames.
    resized_cache: dict[tuple[int, int], Image.Image] = {}

    def _get_sticker(slot: int, radius: int) -> Image.Image:
        diam = max(24, min(230, (radius * 2) & ~1))
        key = (slot, diam)
        cached = resized_cache.get(key)
        if cached is None:
            cached = stickers[slot].resize((diam, diam), Image.Resampling.BILINEAR)
            resized_cache[key] = cached
        return cached

    with tempfile.TemporaryDirectory(prefix="meyaya_solosamba_") as tmpdir:
        out_path = Path(tmpdir) / "meyaya-solosamba.mp4"
        dec_err = Path(tmpdir) / "dec.err"
        enc_err = Path(tmpdir) / "enc.err"

        duration_sec = total_frames / max(1, fps)
        fade_start = max(0.0, duration_sec - 0.4)

        dec_cmd = [
            ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(base_video_path),
            "-t",
            f"{duration_sec + 0.1:.2f}",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "pipe:1",
        ]
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
            "-i",
            str(base_video_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-t",
            f"{duration_sec:.2f}",
            "-vf",
            f"fade=t=out:st={fade_start:.2f}:d=0.4",
            "-af",
            f"afade=t=out:st={fade_start:.2f}:d=0.4",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "superfast",
            "-crf",
            "22",
            "-maxrate",
            "1750k",
            "-bufsize",
            "3500k",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            "-movflags",
            "+faststart",
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
                    faces = faces_by_frame[frame_idx]
                    m_info = meyaya_map.get(str(frame_idx)) if meyaya_frames else None

                    # 1. Background faces behind Meyaya (r <= 44).
                    for cid, cx, cy, r in faces:
                        if cid in stickers and (m_info is None or r <= 44):
                            spr = _get_sticker(cid, r)
                            frame.paste(spr, (cx - spr.width // 2, cy - spr.height // 2), spr)

                    # 2. Animated Chibi Meyaya in the center of the opening circle (F=0..232).
                    if m_info is not None:
                        mx, mfy, mh, ma = m_info
                        t = frame_idx / fps
                        beat = t * BEAT_HZ
                        m_hop = abs(math.sin(math.pi * beat))
                        m_base = meyaya_frames[int(t * 8.0) % len(meyaya_frames)]
                        aspect = m_base.width / max(1, m_base.height)
                        dh = max(32, int(mh * (1.0 + 0.05 * m_hop)))
                        dw = max(24, int(dh * aspect * (1.0 + 0.04 * (1.0 - m_hop))))
                        spr_m = m_base.resize((dw, dh), Image.Resampling.BILINEAR)
                        angle = 7.5 * math.sin(math.pi * beat)
                        spr_m = spr_m.rotate(angle, resample=Image.Resampling.BILINEAR, expand=True)
                        alpha_lut = [int(p * ma) for p in range(256)] if ma < 0.99 else None
                        if alpha_lut is not None:
                            r_ch, g_ch, b_ch, a_ch = spr_m.split()
                            a_ch = a_ch.point(alpha_lut)
                            spr_m = Image.merge("RGBA", (r_ch, g_ch, b_ch, a_ch))
                        # Subtle floor shadow anchored at Meyaya's feet.
                        sw = max(32, int(dw * 0.85 * max(0.6, 1.0 - 0.25 * m_hop)))
                        sh = max(10, int(sw * 0.26))
                        shad = base_shadow.resize((sw, sh), Image.Resampling.BILINEAR)
                        if alpha_lut is not None:
                            sr, sg, sb, sa = shad.split()
                            sa = sa.point(alpha_lut)
                            shad = Image.merge("RGBA", (sr, sg, sb, sa))
                        frame.paste(shad, (int(mx - sw / 2), int(mfy - sh / 2)), shad)
                        jump_px = 14.0 * m_hop
                        frame.paste(
                            spr_m,
                            (int(mx - spr_m.width / 2), int(mfy - spr_m.height - jump_px + 6)),
                            spr_m,
                        )
                        # 3. Foreground faces passing in front of Meyaya (r > 44).
                        for cid, cx, cy, r in faces:
                            if cid in stickers and r > 44:
                                spr = _get_sticker(cid, r)
                                frame.paste(spr, (cx - spr.width // 2, cy - spr.height // 2), spr)

                    enc_proc.stdin.write(frame.tobytes())

                enc_proc.stdin.close()
                dec_proc.stdout.close()
                dec_proc.wait(timeout=15)
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
            "SoloSamba ffmpeg failed dec_rc=%s enc_rc=%s",
            dec_proc.returncode,
            enc_proc.returncode,
        )
    return None


class SoloSambaRenderer:
    """Render face-tracked Solo Samba MP4s with bounded concurrency."""

    def __init__(
        self,
        *,
        base_video_path: Path = DEFAULT_BASE_VIDEO_PATH,
        tracks_path: Path = DEFAULT_TRACKS_PATH,
        meyaya_assets_dir: Path = DISCO_ASSETS_DIR,
        ffmpeg_executable: str = "ffmpeg",
    ) -> None:
        self.base_video_path = base_video_path
        self.tracks_path = tracks_path
        self.meyaya_assets_dir = meyaya_assets_dir
        self.ffmpeg_executable = ffmpeg_executable
        self._semaphore = asyncio.Semaphore(1)

    async def render(
        self,
        dancers: Sequence[DiscoDancer],
        *,
        max_bytes: int = 9 * 1024 * 1024,
    ) -> bytes | None:
        """Render the 27.8s Solo Samba MP4 with the first dancer as the solo star."""
        if not dancers or not self.base_video_path.exists() or not self.tracks_path.exists():
            return None
        if self._semaphore.locked():
            raise DiscoBusyError(
                "The Solo Samba floor is already running another render - try again in a few seconds!"
            )

        ffmpeg_bin = resolve_ffmpeg_executable(self.ffmpeg_executable)
        async with self._semaphore:
            started = time.monotonic()
            try:
                video_bytes = await asyncio.wait_for(
                    animation_work(
                        _render_solosamba_sync,
                        self.base_video_path,
                        self.tracks_path,
                        self.meyaya_assets_dir,
                        list(dancers)[:MAX_CAST],
                        ffmpeg_bin,
                    ),
                    timeout=RENDER_TIMEOUT_SECONDS,
                )
            except (TimeoutError, Exception) as exc:
                logger.warning("SoloSamba render unavailable (%s)", type(exc).__name__)
                return None

            if video_bytes is None or len(video_bytes) > max_bytes:
                return None
            event(
                "solosamba_video_rendered",
                cast=min(len(dancers), MAX_CAST),
                bytes=len(video_bytes),
                render_ms=round((time.monotonic() - started) * 1000, 1),
            )
            return video_bytes
