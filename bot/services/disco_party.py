"""Chaotic 3D Samba disco party 720p video renderer starring Meyaya and server PFPs."""

from __future__ import annotations

import asyncio
import colorsys
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
import logging
import math
from pathlib import Path
import random
import tempfile
import time
from urllib.parse import urlparse

import aiohttp
from PIL import (
    Image,
    ImageDraw,
    ImageEnhance,
    ImageFilter,
    ImageFont,
    ImageOps,
    UnidentifiedImageError,
)

from bot.logging.telemetry import event
from bot.services.gemini_tts import resolve_ffmpeg_executable
from bot.utils.image_work import animation_work

logger = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "disco"
DEFAULT_STAGE_PATH = ASSETS_DIR / "stage.jpg"
DEFAULT_AUDIO_PATH = ASSETS_DIR / "track.m4a"
DEFAULT_MEYAYA_FRAMES = (
    ASSETS_DIR / "meyaya_dancer.png",
    ASSETS_DIR / "meyaya_dancer_2.png",
    ASSETS_DIR / "meyaya_dancer_3.png",
    ASSETS_DIR / "meyaya_dancer_4.png",
)

STAGE_WIDTH = 960
STAGE_HEIGHT = 540
OUTPUT_WIDTH = 1280
OUTPUT_HEIGHT = 720
VIDEO_FPS = 20
VIDEO_DURATION_SECONDS = 17.0
TOTAL_FRAMES = int(VIDEO_FPS * VIDEO_DURATION_SECONDS)
BEAT_HZ = 147.0 / 60.0  # Synced to the 0:43-1:00 Uma Samba chorus drop.

MAX_DANCERS = 6
MAX_AVATAR_BYTES = 6 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
RENDER_TIMEOUT_SECONDS = 45.0
AVATAR_FETCH_TIMEOUT = 5.0

ALLOWED_AVATAR_HOSTS = frozenset({"cdn.discordapp.com", "media.discordapp.net"})

_FONT_CANDIDATES = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    Path("C:/Windows/Fonts/segoeuib.ttf"),
    Path("C:/Windows/Fonts/arialbd.ttf"),
)

_NEON_PALETTE: tuple[tuple[int, int, int], ...] = (
    (255, 84, 198),
    (42, 232, 255),
    (255, 218, 60),
    (176, 108, 255),
    (74, 248, 158),
    (255, 134, 68),
)

# 6 distinct chaotic Samba dance routines assigned across server members.
DANCE_MOVES: tuple[str, ...] = (
    "camera_lunge",
    "orbit_swirl",
    "helicopter_spin",
    "hyper_zigzag",
    "pendulum_swoop",
    "chaotic_headbang",
)


class DiscoBusyError(Exception):
    """Raised when another disco video render is already using the render slot."""


@dataclass(frozen=True, slots=True)
class DiscoDancer:
    """One participant on the 3D rainbow disco stage."""

    user_id: int
    display_name: str
    avatar_bytes: bytes | None = None
    is_meyaya: bool = False


@dataclass(slots=True)
class _Pose3D:
    """3D stage coordinates (wx in [-1.4..1.4], wy >= 0 jump height, wz depth 0.5..2.3)."""

    wx: float
    wy: float
    wz: float
    angle_deg: float
    squash_x: float
    squash_y: float


def _is_safe_avatar_url(url: str) -> bool:
    if not url or len(url) > 2048:
        return False
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname in ALLOWED_AVATAR_HOSTS
        and not parsed.username
        and not parsed.password
        and parsed.port is None
    )


async def fetch_avatar_bytes(
    http_session: aiohttp.ClientSession | None,
    url: str | None,
) -> bytes | None:
    """Safely download a bounded Discord CDN avatar PNG without following redirects."""
    if http_session is None or not url or not _is_safe_avatar_url(url):
        return None
    try:
        async with http_session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=AVATAR_FETCH_TIMEOUT),
            allow_redirects=False,
        ) as response:
            if response.status != 200:
                return None
            length = response.content_length
            if length is not None and length > MAX_AVATAR_BYTES:
                return None
            buf = bytearray()
            async for chunk in response.content.iter_chunked(64 * 1024):
                if len(buf) + len(chunk) > MAX_AVATAR_BYTES:
                    return None
                buf.extend(chunk)
            return bytes(buf) if buf else None
    except (aiohttp.ClientError, TimeoutError):
        return None


@lru_cache(maxsize=4)
def _load_label_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in _FONT_CANDIDATES:
        if candidate.exists():
            try:
                return ImageFont.truetype(str(candidate), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


@lru_cache(maxsize=2)
def _load_stage_variants(path_str: str) -> tuple[Image.Image, ...]:
    """Load the 720p AI disco stage plus pre-lit beat-pulse variants for fast compositing."""
    path = Path(path_str)
    if not path.exists():
        return ()
    try:
        with Image.open(path) as opened:
            base = opened.convert("RGB").resize(
                (STAGE_WIDTH, STAGE_HEIGHT), Image.Resampling.LANCZOS
            )
    except (OSError, UnidentifiedImageError):
        return ()
    # 4 beat-intensity levels (normal -> peak strobe pop) precomputed once!
    variants: list[Image.Image] = []
    for bright, sat in ((0.96, 1.02), (1.03, 1.08), (1.10, 1.14), (1.18, 1.20)):
        img = ImageEnhance.Brightness(base).enhance(bright)
        img = ImageEnhance.Color(img).enhance(sat)
        variants.append(img)
    return tuple(variants)


@lru_cache(maxsize=2)
def _load_meyaya_frames(assets_dir_str: str) -> tuple[Image.Image, ...]:
    """Load Meyaya's animated transparent cutout frames (auto-supports custom meyaya.gif/webp)."""
    root = Path(assets_dir_str)
    frames: list[Image.Image] = []
    for animated_name in ("meyaya.webp", "meyaya.gif"):
        anim_path = root / animated_name
        if anim_path.exists():
            try:
                with Image.open(anim_path) as im:
                    n_frames = getattr(im, "n_frames", 1)
                    for idx in range(min(n_frames, 60)):
                        im.seek(idx)
                        frame = im.convert("RGBA")
                        frame.thumbnail((240, 286), Image.Resampling.LANCZOS)
                        frames.append(frame.copy())
                if frames:
                    return tuple(frames)
            except (OSError, UnidentifiedImageError):
                frames.clear()

    for path in (
        root / "meyaya_dancer.png",
        root / "meyaya_dancer_2.png",
        root / "meyaya_dancer_3.png",
        root / "meyaya_dancer_4.png",
    ):
        if path.exists():
            try:
                with Image.open(path) as im:
                    frame = im.convert("RGBA")
                    frame.thumbnail((240, 286), Image.Resampling.LANCZOS)
                    frames.append(frame.copy())
            except (OSError, UnidentifiedImageError):
                continue
    return tuple(frames)


def _extract_accent_color(avatar: Image.Image, fallback_index: int) -> tuple[int, int, int]:
    small = avatar.convert("RGB").resize((24, 24), Image.Resampling.BILINEAR)
    best_score = -1.0
    best_rgb = _NEON_PALETTE[fallback_index % len(_NEON_PALETTE)]
    for y in range(24):
        for x in range(24):
            raw_px = small.getpixel((x, y))
            if not isinstance(raw_px, tuple) or len(raw_px) < 3:
                continue
            r, g, b = int(raw_px[0]), int(raw_px[1]), int(raw_px[2])
            h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
            score = s * v
            if score > best_score and s > 0.25 and v > 0.25:
                best_score = score
                nr, ng, nb = colorsys.hsv_to_rgb(h, max(0.72, min(0.98, s)), max(0.92, v))
                best_rgb = (int(nr * 255), int(ng * 255), int(nb * 255))
    return best_rgb


def _decode_avatar(raw: bytes | None) -> Image.Image | None:
    if not raw or len(raw) > MAX_AVATAR_BYTES:
        return None
    try:
        with Image.open(BytesIO(raw)) as opened:
            if (
                opened.width <= 0
                or opened.height <= 0
                or opened.width * opened.height > MAX_IMAGE_PIXELS
            ):
                return None
            opened.load()
            return ImageOps.exif_transpose(opened).convert("RGBA")
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError):
        return None


def render_pfp_orb(
    dancer: DiscoDancer,
    index: int,
) -> tuple[Image.Image, tuple[int, int, int]]:
    """Build a razor-sharp glossy circular PFP orb with glowing neon rim (no stick figures!)."""
    orb_size = 240
    avatar_size = 186
    canvas = Image.new("RGBA", (orb_size, orb_size), (0, 0, 0, 0))
    avatar = _decode_avatar(dancer.avatar_bytes)
    accent = (
        _extract_accent_color(avatar, index)
        if avatar is not None
        else _NEON_PALETTE[index % len(_NEON_PALETTE)]
    )
    pad = (orb_size - avatar_size) // 2

    # 1. Vibrant outer neon aura bloom.
    glow = Image.new("RGBA", (orb_size, orb_size), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        (pad - 14, pad - 14, pad + avatar_size + 14, pad + avatar_size + 14),
        fill=(*accent, 210),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(radius=12))
    canvas = Image.alpha_composite(canvas, glow)

    draw = ImageDraw.Draw(canvas)
    # 2. Crisp dark outer stroke + glowing neon ring + clean white sticker border.
    draw.ellipse(
        (pad - 10, pad - 10, pad + avatar_size + 10, pad + avatar_size + 10),
        fill=(*accent, 255),
        outline=(20, 12, 34, 255),
        width=4,
    )
    draw.ellipse(
        (pad - 4, pad - 4, pad + avatar_size + 4, pad + avatar_size + 4),
        fill=(255, 255, 255, 255),
    )

    if avatar is not None:
        fitted = ImageOps.fit(avatar, (avatar_size, avatar_size), method=Image.Resampling.LANCZOS)
    else:
        fitted = Image.new("RGBA", (avatar_size, avatar_size), (*accent, 255))
        fdraw = ImageDraw.Draw(fitted)
        initial = (dancer.display_name[:1] or "?").upper()
        ifont = _load_label_font(86)
        ib = fdraw.textbbox((0, 0), initial, font=ifont)
        fdraw.text(
            ((avatar_size - (ib[2] - ib[0])) // 2 - ib[0], (avatar_size - (ib[3] - ib[1])) // 2 - ib[1]),
            initial,
            font=ifont,
            fill=(255, 255, 255, 255),
        )

    mask_hi = Image.new("L", (avatar_size * 2, avatar_size * 2), 0)
    ImageDraw.Draw(mask_hi).ellipse((0, 0, avatar_size * 2 - 1, avatar_size * 2 - 1), fill=255)
    mask = mask_hi.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
    canvas.paste(fitted, (pad, pad), mask)

    # 3. Subtle glossy specular arc across upper circle.
    gloss = Image.new("RGBA", (orb_size, orb_size), (0, 0, 0, 0))
    ImageDraw.Draw(gloss).ellipse(
        (pad + 24, pad + 10, pad + avatar_size - 24, pad + 62),
        fill=(255, 255, 255, 46),
    )
    canvas = Image.alpha_composite(canvas, gloss)
    return canvas, accent


def _render_name_badge(label: str, accent: tuple[int, int, int]) -> Image.Image:
    clean = " ".join((label or "Dancer").split()).strip()[:14] or "Dancer"
    font = _load_label_font(20)
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bbox = tmp.textbbox((0, 0), clean, font=font)
    tw = max(1, int(bbox[2] - bbox[0]))
    th = max(1, int(bbox[3] - bbox[1]))
    pw, ph = tw + 26, th + 12
    badge = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    draw = ImageDraw.Draw(badge)
    draw.rounded_rectangle(
        (0, 0, pw - 1, ph - 1),
        radius=ph // 2,
        fill=(14, 9, 26, 215),
        outline=(*accent, 240),
        width=2,
    )
    draw.text(
        ((pw - tw) // 2 - int(bbox[0]), (ph - th) // 2 - int(bbox[1])),
        clean,
        font=font,
        fill=(255, 252, 255, 255),
    )
    return badge


@lru_cache(maxsize=1)
def _base_shadow_sprite() -> Image.Image:
    """Tiny reusable soft floor shadow sprite (avoids allocating full 1280x720 RGBA per frame)."""
    img = Image.new("RGBA", (160, 48), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((12, 8, 148, 40), fill=(8, 4, 22, 145))
    return img.filter(ImageFilter.GaussianBlur(radius=5))


def _pose_for_move(move: str, t: float, slot_idx: int, total_users: int) -> _Pose3D:
    """Compute chaotic 3D Samba world position (wx, wy, wz), spin/tilt, and squash-stretch."""
    beat = t * BEAT_HZ
    phase = slot_idx * 1.15
    side = -1.0 if slot_idx % 2 == 0 else 1.0
    spread = 0.72 if total_users <= 2 else 0.92

    if move == "camera_lunge":
        # Bounces on mid-floor, then SUDDENLY ROCKETS HUGE into the camera lens like Gold Ship!
        cycle = (t * 0.34 + slot_idx * 0.21) % 1.0
        lunge = math.pow(max(0.0, math.sin(cycle * math.pi)), 4.0)
        wz = 1.68 - 1.12 * lunge  # 1.68 (small) -> 0.56 (HUGE close-up!)
        wx = side * (0.82 - 0.34 * lunge) + 0.14 * math.sin(beat * math.pi + phase)
        hop = abs(math.sin(beat * math.pi + phase))
        wy = 0.24 * hop + 0.12 * lunge * abs(math.sin(beat * 2.0 * math.pi))
        angle = (14.0 + 18.0 * lunge) * math.sin(beat * (2.0 if lunge > 0.4 else 1.0) * math.pi + phase)
        return _Pose3D(wx, wy, wz, angle, 1.0 + 0.12 * (1.0 - hop), 1.0 + 0.12 * hop)

    if move == "orbit_swirl":
        # Giant 3D ring orbit: sweeps small BEHIND Meyaya and HUGE right in FRONT of Meyaya!
        theta = t * 1.35 + phase
        wx = math.sin(theta) * 1.18
        wz = 1.34 + math.cos(theta) * 0.74  # 0.60 (huge front!) <-> 2.08 (small back!)
        hop = abs(math.sin(beat * math.pi + phase))
        wy = 0.26 * hop
        angle = 20.0 * math.sin(beat * math.pi + phase)
        return _Pose3D(wx, wy, wz, angle, 1.0 + 0.10 * (1.0 - hop), 1.0 + 0.10 * hop)

    if move == "helicopter_spin":
        # Continuous wild 360-degree samba spin leaping across the floor in a diagonal figure-8!
        wx = math.sin(t * 1.6 + phase) * 1.15
        wz = 1.25 + math.sin(t * 3.2 + phase) * 0.56  # 0.69 (big) <-> 1.81 (small)
        hop = abs(math.sin(beat * math.pi + phase))
        wy = 0.34 * hop
        angle = (t * 420.0 * side) % 360.0
        return _Pose3D(wx, wy, wz, angle, 1.05, 0.96)

    if move == "hyper_zigzag":
        # Double-time caffeinated squash-and-stretch hops zipping back & forth!
        hop = abs(math.sin(beat * 1.5 * math.pi + phase))
        wx = math.sin(t * 2.35 + phase) * (1.12 * spread)
        wz = 1.12 + 0.62 * math.cos(t * 1.7 + phase)
        wy = 0.30 * hop
        angle = 24.0 * math.cos(beat * 1.5 * math.pi + phase)
        return _Pose3D(wx, wy, wz, angle, 1.0 + 0.16 * (1.0 - hop), 1.0 + 0.18 * hop)

    if move == "pendulum_swoop":
        # High parabolic stage swoop from back corners -> HUGE front foreground!
        swing = math.sin(t * 1.15 + phase)
        wx = swing * 1.22
        wz = 0.64 + 1.25 * (swing * swing)  # Huge in center foreground, small at sides!
        hop = abs(math.sin(beat * math.pi + phase))
        wy = 0.22 * (1.0 - swing * swing) + 0.24 * hop
        angle = -28.0 * swing + 12.0 * math.sin(beat * math.pi)
        return _Pose3D(wx, wy, wz, angle, 1.0 + 0.10 * (1.0 - hop), 1.0 + 0.12 * hop)

    # chaotic_headbang: rapid tilted headbanging + sudden energetic dance-floor spot hops!
    bar = int(beat / 4.0)
    spots = (
        (-0.95, 0.72),
        (0.92, 1.75),
        (-0.52, 1.88),
        (0.88, 0.66),
        (0.15, 0.62),
        (-1.05, 1.45),
    )
    tx, tz = spots[(bar + slot_idx) % len(spots)]
    px, pz = spots[(bar - 1 + slot_idx) % len(spots)]
    frac = min(1.0, ((beat / 4.0) - bar) * 3.5)
    ease = 1.0 - (1.0 - frac) ** 3
    wx = px + (tx - px) * ease
    wz = pz + (tz - pz) * ease
    hop = abs(math.sin(beat * math.pi + phase))
    wy = 0.28 * hop + 0.22 * math.sin(frac * math.pi)
    angle = 26.0 * math.sin(beat * 2.0 * math.pi + phase)
    return _Pose3D(wx, wy, wz, angle, 1.0 + 0.14 * (1.0 - hop), 1.0 + 0.14 * hop)


def _project_3d(wx: float, wy: float, wz: float) -> tuple[float, float, float, float]:
    """Project 3D floor point to (screen_x, floor_y, sprite_y, perspective_scale)."""
    depth = max(0.45, wz)
    inv = 1.15 / depth
    sx = STAGE_WIDTH * 0.5 + wx * (STAGE_WIDTH * 0.33) * inv
    # Floor horizon ~0.576H, foreground edge ~0.97H.
    floor_y = STAGE_HEIGHT * 0.576 + (STAGE_HEIGHT * 0.326) * min(1.38, inv)
    sprite_y = floor_y - wy * (STAGE_HEIGHT * 0.23) * inv
    return sx, floor_y, sprite_y, inv


def _render_badge_tiers(badge: Image.Image) -> tuple[Image.Image, Image.Image, Image.Image]:
    """Pre-scale 3 discrete depth tiers (far/mid/near) to avoid per-frame badge resampling."""
    tiers: list[Image.Image] = []
    for scale in (0.64, 0.82, 1.0):
        bw = max(36, int(badge.width * scale))
        bh = max(16, int(badge.height * scale))
        tiers.append(badge.resize((bw, bh), Image.Resampling.LANCZOS))
    return (tiers[0], tiers[1], tiers[2])


def _render_video_frames_sync(
    stage_path: Path,
    assets_dir: Path,
    dancers: list[DiscoDancer],
    audio_path: Path | None,
    ffmpeg_bin: str,
) -> bytes | None:
    """Render all 340 frames with true 3D Z-sorted PFP chaos and encode 720p MP4 via ffmpeg."""
    variants = _load_stage_variants(str(stage_path))
    if not variants:
        return None
    meyaya_frames = _load_meyaya_frames(str(assets_dir))

    # Build circular PFP orbs + 3-tier depth badges once!
    user_dancers = [d for d in dancers if not d.is_meyaya][:MAX_DANCERS]
    orbs: list[
        tuple[
            DiscoDancer,
            Image.Image,
            tuple[Image.Image, Image.Image, Image.Image],
            tuple[int, int, int],
            str,
        ]
    ] = []
    for idx, dancer in enumerate(user_dancers):
        orb_img, accent = render_pfp_orb(dancer, idx)
        badge_tiers = _render_badge_tiers(_render_name_badge(dancer.display_name, accent))
        move = DANCE_MOVES[idx % len(DANCE_MOVES)]
        orbs.append((dancer, orb_img, badge_tiers, accent, move))

    meyaya_badge = _render_badge_tiers(_render_name_badge("Meyaya", (255, 118, 206)))[1]
    base_shadow = _base_shadow_sprite()

    # Pre-seed dynamic rainbow confetti particles.
    rng = random.Random(147)
    confetti = [
        (
            rng.uniform(0, STAGE_WIDTH),
            rng.uniform(0, STAGE_HEIGHT),
            rng.uniform(36, 102),
            rng.uniform(-32, 32),
            rng.uniform(0.0, math.tau),
            rng.uniform(3.2, 6.8),
            _NEON_PALETTE[i % len(_NEON_PALETTE)],
        )
        for i in range(36)
    ]

    has_audio = audio_path is not None and audio_path.exists()
    with tempfile.TemporaryDirectory(prefix="meyaya_disco_") as tmpdir:
        out_path = Path(tmpdir) / "meyaya-disco.mp4"
        err_path = Path(tmpdir) / "ffmpeg.err"
        # Upscale to 720p HD with Uma-Samba Dutch-angle camera sway in C/SIMD inside ffmpeg!
        cam_vf = (
            f"scale=1380:776:flags=bicubic,"
            f"rotate='0.036*sin(1.65*t)':bilinear=1:ow=1380:oh=776,"
            f"crop={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(iw-{OUTPUT_WIDTH})/2:(ih-{OUTPUT_HEIGHT})/2"
        )
        cmd: list[str] = [
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
            f"{STAGE_WIDTH}x{STAGE_HEIGHT}",
            "-r",
            str(VIDEO_FPS),
            "-i",
            "pipe:0",
        ]
        if has_audio and audio_path is not None:
            cmd.extend(
                ["-i", str(audio_path), "-map", "0:v:0", "-map", "1:a:0", "-c:a", "copy", "-shortest"]
            )
        else:
            cmd.append("-an")
        cmd.extend(
            [
                "-vf",
                cam_vf,
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-preset",
                "superfast",
                "-crf",
                "22",
                "-maxrate",
                "2400k",
                "-bufsize",
                "4800k",
                "-movflags",
                "+faststart",
                str(out_path),
            ]
        )

        import subprocess

        with err_path.open("wb") as err_file:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=err_file)
            assert proc.stdin is not None
            try:
                for frame_idx in range(TOTAL_FRAMES):
                    t = frame_idx / VIDEO_FPS
                    beat = t * BEAT_HZ
                    beat_pulse = math.pow(abs(math.sin(math.pi * beat)), 2.4)
                    var_idx = min(len(variants) - 1, int(beat_pulse * len(variants)))
                    frame = variants[var_idx].copy()

                    # Collect all drawables with 3D depth `wz` so we Z-sort back-to-front!
                    draw_queue: list[
                        tuple[
                            float,
                            str,
                            _Pose3D,
                            Image.Image | None,
                            tuple[Image.Image, Image.Image, Image.Image] | None,
                        ]
                    ] = []

                    # 1. Center Star: User's exact Chibi Meyaya!
                    if meyaya_frames:
                        m_hop = abs(math.sin(math.pi * beat))
                        m_pose = _Pose3D(
                            wx=0.12 * math.sin(math.pi * beat * 0.5),
                            wy=0.18 * m_hop,
                            wz=1.12,
                            angle_deg=9.0 * math.sin(math.pi * beat),
                            squash_x=1.0 + 0.08 * (1.0 - m_hop),
                            squash_y=1.0 + 0.09 * m_hop,
                        )
                        draw_queue.append((m_pose.wz, "meyaya", m_pose, None, None))

                    # 2. All user circular PFPs doing their own chaotic 3D Samba moves!
                    for idx, (_, orb_img, badge_tiers, _, move) in enumerate(orbs):
                        pose = _pose_for_move(move, t, idx, len(orbs))
                        draw_queue.append((pose.wz, "pfp", pose, orb_img, badge_tiers))

                    # Sort furthest (largest wz = smallest) -> closest (smallest wz = HUGE foreground)!
                    draw_queue.sort(key=lambda item: -item[0])

                    # Draw every dancer + ground shadow in strict back-to-front 3D order!
                    for _, kind, item_pose, item_orb, item_badges in draw_queue:
                        sx, floor_y, sprite_y, scale = _project_3d(
                            item_pose.wx, item_pose.wy, item_pose.wz
                        )
                        air_shrink = max(0.45, 1.0 - item_pose.wy * 1.1)
                        sw = max(28, int(118 * scale * air_shrink))
                        sh = max(10, int(32 * scale * air_shrink))
                        shad = base_shadow.resize((sw, sh), Image.Resampling.BILINEAR)
                        frame.paste(shad, (int(sx - sw / 2), int(floor_y - sh / 2)), shad)

                        if kind == "meyaya":
                            m_idx = int(t * 8.0) % len(meyaya_frames)
                            base_m = meyaya_frames[m_idx]
                            mw = max(38, int(base_m.width * scale * 0.96 * item_pose.squash_x))
                            mh = max(48, int(base_m.height * scale * 0.96 * item_pose.squash_y))
                            resized = base_m.resize((mw, mh), Image.Resampling.BILINEAR)
                            rotated = resized.rotate(
                                item_pose.angle_deg, resample=Image.Resampling.BILINEAR, expand=True
                            )
                            px = int(sx - rotated.width / 2)
                            py = int(sprite_y - rotated.height + 12 * scale)
                            frame.paste(rotated, (px, py), rotated)
                            bx = int(sx - meyaya_badge.width / 2)
                            by = min(STAGE_HEIGHT - meyaya_badge.height - 34, int(floor_y + 6))
                            frame.paste(meyaya_badge, (bx, by), meyaya_badge)
                        elif item_orb is not None and item_badges is not None:
                            ow = max(44, min(244, int(144 * scale * item_pose.squash_x)))
                            oh = max(44, min(244, int(144 * scale * item_pose.squash_y)))
                            resized = item_orb.resize((ow, oh), Image.Resampling.BILINEAR)
                            rotated = resized.rotate(
                                item_pose.angle_deg, resample=Image.Resampling.BILINEAR, expand=True
                            )
                            px = int(sx - rotated.width / 2)
                            py = int(sprite_y - rotated.height * 0.84)
                            frame.paste(rotated, (px, py), rotated)
                            tier_idx = 0 if scale < 0.82 else (1 if scale < 1.28 else 2)
                            b_img = item_badges[tier_idx]
                            bx = max(32, min(STAGE_WIDTH - b_img.width - 32, int(sx - b_img.width / 2)))
                            by = min(
                                STAGE_HEIGHT - b_img.height - 34,
                                max(30, int(py + rotated.height - 14)),
                            )
                            frame.paste(b_img, (bx, by), b_img)

                    # Flying glowing rainbow confetti & beat-drop sparkles!
                    cdraw = ImageDraw.Draw(frame)
                    for cx0, cy0, vy, vx, ph, sz, rgb in confetti:
                        cx = (cx0 + t * vx + math.sin(t * 3.5 + ph) * 20.0) % STAGE_WIDTH
                        cy = (cy0 + t * vy) % STAGE_HEIGHT
                        s = sz * (0.75 + 0.45 * beat_pulse)
                        cdraw.ellipse((cx - s, cy - s, cx + s, cy + s), fill=rgb)

                    proc.stdin.write(frame.tobytes())

                proc.stdin.close()
                proc.wait(timeout=20)
            except Exception:
                with suppress(OSError):
                    proc.kill()
                with suppress(OSError, subprocess.TimeoutExpired):
                    proc.wait(timeout=2)
                raise
        if proc.returncode == 0 and out_path.exists():
            data = out_path.read_bytes()
            if data:
                return data
        if err_path.exists() and err_path.stat().st_size > 0:
            logger.warning("Disco ffmpeg render failed code=%s", proc.returncode)
    return None


class DiscoPartyRenderer:
    """Render high-quality chaotic 3D Samba disco party MP4s with bounded concurrency."""

    def __init__(
        self,
        *,
        stage_path: Path = DEFAULT_STAGE_PATH,
        assets_dir: Path = ASSETS_DIR,
        audio_path: Path | None = None,
        ffmpeg_executable: str = "ffmpeg",
    ) -> None:
        self.stage_path = stage_path
        self.assets_dir = assets_dir
        self.audio_path = audio_path if audio_path is not None else DEFAULT_AUDIO_PATH
        self.ffmpeg_executable = ffmpeg_executable
        self._semaphore = asyncio.Semaphore(1)

    async def render(
        self,
        dancers: Sequence[DiscoDancer],
        *,
        max_bytes: int = 9 * 1024 * 1024,
    ) -> bytes | None:
        """Render a 17s 720p 24fps chaotic 3D Samba MP4 with Meyaya + circular server PFPs."""
        if not dancers or not self.stage_path.exists():
            return None
        if self._semaphore.locked():
            raise DiscoBusyError(
                "The disco floor is already spinning for another render - try again in a few seconds!"
            )

        ffmpeg_bin = resolve_ffmpeg_executable(self.ffmpeg_executable)
        async with self._semaphore:
            started = time.monotonic()
            try:
                video_bytes = await asyncio.wait_for(
                    animation_work(
                        _render_video_frames_sync,
                        self.stage_path,
                        self.assets_dir,
                        list(dancers)[: MAX_DANCERS + 1],
                        self.audio_path,
                        ffmpeg_bin,
                    ),
                    timeout=RENDER_TIMEOUT_SECONDS,
                )
            except (TimeoutError, Exception) as exc:
                logger.warning("Disco render unavailable (%s)", type(exc).__name__)
                return None

            if video_bytes is None or len(video_bytes) > max_bytes:
                return None
            event(
                "disco_video_rendered",
                dancers=min(len(dancers), MAX_DANCERS),
                bytes=len(video_bytes),
                render_ms=round((time.monotonic() - started) * 1000, 1),
                has_audio=self.audio_path.exists(),
            )
            return video_bytes
