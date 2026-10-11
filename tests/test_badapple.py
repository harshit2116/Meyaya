"""Synthetic media and mocked Discord only; never require credentials or real media."""

from __future__ import annotations

import asyncio
import gzip
import itertools
import json
import os
import shutil
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest
from discord.ext import commands
from PIL import Image

from bot.cogs.badapple import BadAppleCog
from bot.services.badapple import BadApplePlayer, PlaybackBusy
from bot.utils.badapple import (
    Animation,
    MediaError,
    image_to_braille,
    load_animation,
    render_content,
    validate_dimensions,
    validate_frame,
)
from scripts.preprocess_badapple import preprocess, probe_video


def cache_file(tmp_path, frames=None, **metadata):
    frames = frames if frames is not None else ["\u2800", "\u28ff", "\u2801"]
    path = tmp_path / "frames.jsonl.gz"
    header = {"version": 1, "width": 1, "height": 1, "fps": 1, "duration": len(frames)}
    header.update(metadata)
    write_records(path, [header, *frames, {"frames": len(frames)}])
    return path


def write_records(path, records):
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def test_braille_dot_mapping_and_dimensions():
    image = Image.new("L", (2, 4), 0)
    for xy, bit in [
        ((0, 0), 1),
        ((0, 1), 2),
        ((0, 2), 4),
        ((1, 0), 8),
        ((1, 1), 16),
        ((1, 2), 32),
        ((0, 3), 64),
        ((1, 3), 128),
    ]:
        image.paste(0, (0, 0, 2, 4))
        image.putpixel(xy, 255)
        assert image_to_braille(image, 1, 1) == chr(0x2800 + bit)
    frame = image_to_braille(Image.new("L", (100, 75), 255), 48, 18)
    validate_frame(frame, 48, 18)
    assert frame == image_to_braille(Image.new("L", (100, 75), 255), 48, 18)
    assert frame == "\n".join(["\u28ff" * 48] * 18)


def test_letterbox_and_threshold():
    wide = Image.new("L", (16, 4), 127)
    assert image_to_braille(wide, 2, 2, 128) == "\u2800\u2800\n\u2800\u2800"
    assert image_to_braille(wide, 2, 2, 127) != "\u28ff\u28ff\n\u28ff\u28ff"
    with pytest.raises(MediaError, match="Threshold"):
        image_to_braille(wide, 2, 2, 256)


@pytest.mark.parametrize("size", [(0, 1), (1, -1), (80, 40), (True, 1)])
def test_invalid_dimensions(size):
    with pytest.raises(MediaError):
        validate_dimensions(*size)


def test_content_budget_includes_formatting():
    assert len(render_content("\u28ff" * 1799, "Complete")) <= 2000
    with pytest.raises(MediaError):
        render_content("\u28ff" * 1999, "Complete")


def test_cache_loads_full_ordered_sequence(tmp_path):
    frames = [chr(0x2800 + index % 256) for index in range(220)]
    animation = load_animation(cache_file(tmp_path, frames))
    assert animation.frames == tuple(frames)
    assert animation.duration == 220


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"not gzip",
        gzip.compress(b"not json\n"),
        gzip.compress(b"{}\n"),
        gzip.compress(b"[]\n"),
    ],
)
def test_corrupt_cache(tmp_path, payload):
    path = tmp_path / "broken.gz"
    path.write_bytes(payload)
    with pytest.raises(MediaError):
        load_animation(path)


def test_missing_cache(tmp_path):
    with pytest.raises(MediaError):
        load_animation(tmp_path / "absent.gz")


@pytest.mark.parametrize(
    "metadata",
    [
        {"width": 0},
        {"width": "1"},
        {"fps": 0},
        {"fps": 6.01},
        {"fps": float("nan")},
        {"duration": float("inf")},
        {"duration": 200},
        {"version": 2},
    ],
)
def test_invalid_metadata(tmp_path, metadata):
    with pytest.raises(MediaError):
        load_animation(cache_file(tmp_path, **metadata))


@pytest.mark.parametrize("frames", [[], ["text"], ["```"], ["\u2800\u2800"], [5]])
def test_empty_or_malformed_frames(tmp_path, frames):
    with pytest.raises(MediaError):
        load_animation(cache_file(tmp_path, frames, duration=1))


def test_truncated_extra_and_oversized_cache(tmp_path):
    path = cache_file(tmp_path)
    original = path.read_bytes()
    path.write_bytes(original[:-6])
    with pytest.raises(MediaError):
        load_animation(path)
    path = cache_file(tmp_path)
    with gzip.open(path, "ab") as stream:
        stream.write(b"junk\n")
    with pytest.raises(MediaError):
        load_animation(path)
    path.write_bytes(gzip.compress(b" " * 20_000))
    with pytest.raises(MediaError):
        load_animation(path)


def test_memory_and_count_limits(tmp_path, monkeypatch):
    path = cache_file(tmp_path)
    monkeypatch.setattr("bot.utils.badapple.MAX_CHARACTERS", 2)
    with pytest.raises(MediaError, match="budget"):
        load_animation(path)
    monkeypatch.setattr("bot.utils.badapple.MAX_CHARACTERS", 100)
    monkeypatch.setattr("bot.utils.badapple.MAX_FRAMES", 2)
    with pytest.raises(MediaError, match="budget"):
        load_animation(path)


@pytest.fixture
def media_tools():
    ffmpeg = os.environ.get("TEST_FFMPEG") or shutil.which("ffmpeg")
    ffprobe = os.environ.get("TEST_FFPROBE") or shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip(
            "Synthetic video integration needs FFmpeg/ffprobe (or TEST_FFMPEG/TEST_FFPROBE)"
        )
    return ffmpeg, ffprobe


@pytest.fixture
def video(tmp_path, media_tools):
    ffmpeg, _ = media_tools
    path = tmp_path / "synthetic.avi"
    pixels = bytes(64) * 4 + bytes([255]) * 64 * 4 + bytes([255, 0] * 32) * 4
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "rawvideo",
            "-pixel_format",
            "gray",
            "-video_size",
            "8x8",
            "-framerate",
            "4",
            "-i",
            "pipe:0",
            "-an",
            "-c:v",
            "ffv1",
            str(path),
        ],
        input=pixels,
        check=True,
        timeout=30,
    )
    return path


def test_complete_deterministic_video_preprocessing(tmp_path, video, media_tools, monkeypatch):
    import socket

    def no_network(*args, **kwargs):
        pytest.fail("Preprocessing attempted a network connection")

    monkeypatch.setattr(socket, "create_connection", no_network)
    ffmpeg, ffprobe = media_tools
    first, second = tmp_path / "a.gz", tmp_path / "b.gz"
    for output in (first, second):
        count, duration = preprocess(
            video, output, width=4, height=2, fps=1, ffmpeg=ffmpeg, ffprobe=ffprobe
        )
        assert count == 3
        assert duration == 3
    assert first.read_bytes() == second.read_bytes()
    frames = load_animation(first).frames
    assert frames[0] == "\u2800" * 4 + "\n" + "\u2800" * 4
    assert frames[1] == "\u28ff" * 4 + "\n" + "\u28ff" * 4
    assert frames[2] not in frames[:2]
    with pytest.raises(MediaError, match="already exists"):
        preprocess(video, first, ffprobe=ffprobe)
    original = first.read_bytes()
    with pytest.raises(MediaError, match="ffmpeg is unavailable"):
        preprocess(video, first, overwrite=True, ffprobe=ffprobe, ffmpeg="missing-ffmpeg")
    assert first.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))


def test_auto_height_and_fractional_sampling(tmp_path, video, media_tools):
    ffmpeg, ffprobe = media_tools
    output = tmp_path / "fractional.gz"
    count, _ = preprocess(video, output, width=4, fps=0.5, ffmpeg=ffmpeg, ffprobe=ffprobe)
    animation = load_animation(output)
    assert animation.height == 2 and count == 2


@pytest.mark.parametrize("contents", [None, b"", b"broken video"])
def test_missing_empty_corrupt_video(tmp_path, media_tools, contents):
    path = tmp_path / "invalid.mp4"
    if contents is not None:
        path.write_bytes(contents)
    with pytest.raises(MediaError):
        probe_video(path, media_tools[1])


def test_no_decodable_frames_or_shortened_video(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.preprocess_badapple.probe_video", lambda *args: (3, 1))
    process = SimpleNamespace(
        stdout=SimpleNamespace(read=lambda _: b"", close=lambda: None),
        kill=lambda: None,
        wait=lambda: 0,
        poll=lambda: 0,
    )
    monkeypatch.setattr("scripts.preprocess_badapple.subprocess.Popen", lambda *a, **kw: process)
    with pytest.raises(MediaError, match="empty animation"):
        preprocess(tmp_path / "input", tmp_path / "empty.gz")
    assert not (tmp_path / "empty.gz").exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_preprocessor_import_has_no_bot_or_service_dependencies():
    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import scripts.preprocess_badapple, sys; "
                "assert not any(name in sys.modules for name in "
                "('bot.app', 'bot.config.settings', 'redis', 'sqlalchemy', 'discord'))"
            ),
        ],
        check=True,
        timeout=30,
    )


@pytest.fixture
def fast_clock(monkeypatch):
    clock = SimpleNamespace(now=0.0, sleeps=[])
    original_sleep = asyncio.sleep

    async def sleep(delay):
        assert delay >= 0
        clock.sleeps.append(delay)
        clock.now += delay
        await original_sleep(0)

    monkeypatch.setattr("bot.services.badapple.monotonic", lambda: clock.now)
    monkeypatch.setattr("bot.services.badapple.asyncio.sleep", sleep)
    return clock


@pytest.mark.asyncio
@pytest.mark.parametrize("latency", [0.0, 2.5])
async def test_order_completion_and_latency_no_skips(fast_clock, latency):
    player = BadApplePlayer()
    animation = Animation(1, 1, 1, 3, ("\u2800", "\u28ff", "\u2801"))
    starts = []

    async def edit(**kwargs):
        starts.append(fast_clock.now)
        fast_clock.now += latency

    message = SimpleNamespace(edit=AsyncMock(side_effect=edit))
    async with player.reserve(1, 2):
        result = await player.play(message, animation, 1)
    edits = message.edit.call_args_list
    assert [call.kwargs["content"].split("\n")[1] for call in edits[:3]] == list(animation.frames)
    assert "Complete" in edits[-1].kwargs["content"]
    assert all(b - a >= 1 for a, b in itertools.pairwise(starts))
    assert result.actual_fps == pytest.approx(1 / (latency + 1) if latency else 1)
    assert player.task is None and player.owner_id is None


@pytest.mark.asyncio
async def test_duplicate_cancellation_and_unload_cleanup():
    player = BadApplePlayer()
    started = asyncio.Event()

    async def edit(**kwargs):
        if "Cancelled" not in kwargs["content"]:
            started.set()
            await asyncio.Event().wait()

    message = SimpleNamespace(edit=AsyncMock(side_effect=edit))

    async def run():
        async with player.reserve(1, 2):
            await player.play(message, Animation(1, 1, 1, 1, ("\u2800",)), 1)

    task = asyncio.create_task(run())
    await started.wait()
    with pytest.raises(PlaybackBusy):
        async with player.reserve(3, 4):
            pytest.fail("Concurrent playback acquired the slot")
    await player.close()
    assert task.cancelled()
    assert player.task is None and player.channel_id is None
    assert "Cancelled" in message.edit.call_args.kwargs["content"]
    with pytest.raises(PlaybackBusy):
        async with player.reserve(1, 2):
            pass


@pytest.mark.asyncio
async def test_cancel_during_cache_load_holds_slot(tmp_path, monkeypatch):
    import threading

    player = BadApplePlayer()
    started, release = threading.Event(), threading.Event()
    finished = threading.Event()

    def load(path):
        started.set()
        release.wait(5)
        finished.set()
        raise MediaError("late error")

    monkeypatch.setattr("bot.services.badapple.load_animation", load)

    async def run():
        async with player.reserve(1, 2):
            await player.load(tmp_path / "cache")

    task = asyncio.create_task(run())
    try:
        await asyncio.to_thread(started.wait, 5)
        task.cancel()
        await asyncio.sleep(0)
        assert player.task is task
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set() and player.task is None
    finally:
        release.set()


def http_error(status):
    return discord.HTTPException(SimpleNamespace(status=status, reason="test"), "test")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        http_error(429),
        http_error(403),
        http_error(404),
        http_error(500),
        discord.RateLimited(30),
        TimeoutError(),
    ],
)
async def test_api_failures_release_slot_without_retry(error):
    player = BadApplePlayer()
    message = SimpleNamespace(edit=AsyncMock(side_effect=error))
    with pytest.raises(type(error)):
        async with player.reserve(1, 2):
            await player.play(message, Animation(1, 1, 1, 1, ("\u2800",)), 1)
    assert player.task is None
    assert message.edit.await_count == 1


def context(owner=1, moderator=False, allowed=True):
    permissions = SimpleNamespace(
        view_channel=allowed, send_messages=allowed, manage_messages=moderator
    )
    return SimpleNamespace(
        author=SimpleNamespace(id=owner),
        me=SimpleNamespace(id=10),
        channel=SimpleNamespace(id=2, permissions_for=lambda _: permissions, send=AsyncMock()),
        interaction=SimpleNamespace(is_expired=lambda: False),
        defer=AsyncMock(),
        send=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_command_uses_one_bot_message(tmp_path, fast_clock):
    path = cache_file(tmp_path)
    cog = BadAppleCog(
        SimpleNamespace(settings=SimpleNamespace(badapple_cache_path=path, badapple_fps=1))
    )
    ctx = context()
    message = SimpleNamespace(edit=AsyncMock())
    ctx.channel.send.return_value = message
    await cog.badapple.callback(cog, ctx)
    ctx.defer.assert_awaited_once_with(ephemeral=True)
    assert ctx.channel.send.await_count == 1
    assert message.edit.await_count == 4
    assert cog.player.task is None


@pytest.mark.asyncio
async def test_command_missing_media_and_permissions(tmp_path):
    cog = BadAppleCog(
        SimpleNamespace(settings=SimpleNamespace(badapple_cache_path=tmp_path / "missing"))
    )
    ctx = context()
    await cog.badapple.callback(cog, ctx)
    assert "unavailable" in ctx.send.call_args.args[0]
    ctx.channel.send.assert_not_awaited()
    assert cog.player.task is None
    denied = context(allowed=False)
    await cog.badapple.callback(cog, denied)
    assert "permissions" in denied.send.call_args.args[0]


@pytest.mark.asyncio
async def test_stop_authorization_and_channel():
    cog = BadAppleCog(SimpleNamespace())
    cog.player.task = SimpleNamespace()
    cog.player.owner_id, cog.player.channel_id = 1, 2
    cog.player.stop = AsyncMock()
    denied = context(owner=3)
    await cog.badapplestop.callback(cog, denied)
    cog.player.stop.assert_not_awaited()
    for ctx in [context(), context(owner=3, moderator=True)]:
        await cog.badapplestop.callback(cog, ctx)
    assert cog.player.stop.await_count == 2
    cog.player.channel_id = 100
    await cog.badapplestop.callback(cog, denied)
    assert "No Bad Apple" in denied.send.call_args.args[0]


@pytest.mark.asyncio
async def test_extension_loads_without_media_or_connections(tmp_path):
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    async with bot:
        await bot.load_extension("bot.cogs.badapple")
        assert bot.tree.get_command("badapple") is not None
        assert bot.tree.get_command("badapplestop") is not None
        await bot.unload_extension("bot.cogs.badapple")
        assert bot.tree.get_command("badapple") is None


@pytest.mark.asyncio
async def test_full_220_second_pipeline(tmp_path, media_tools, fast_clock):
    ffmpeg, ffprobe = media_tools
    source, output = tmp_path / "long.avi", tmp_path / "long.gz"
    await asyncio.to_thread(
        subprocess.run,
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=64x48:rate=4",
            "-t",
            "220",
            "-c:v",
            "ffv1",
            str(source),
        ],
        check=True,
        timeout=30,
    )
    count, duration = preprocess(source, output, width=48, ffmpeg=ffmpeg, ffprobe=ffprobe)
    assert (count, duration) == (220, 220)
    player = BadApplePlayer()
    message = SimpleNamespace(edit=AsyncMock())
    async with player.reserve(1, 2):
        animation = await player.load(output)
        result = await player.play(message, animation, 1)
    assert result.frames == 220 and result.seconds == 220
    assert message.edit.await_count == 221
    assert all(
        call.kwargs["content"].startswith(f"```\n{frame}\n```")
        for call, frame in zip(message.edit.call_args_list, animation.frames)
    )
    assert "Complete" in message.edit.call_args.kwargs["content"]


@pytest.mark.asyncio
async def test_command_api_error_and_duplicate_response(tmp_path):
    cog = BadAppleCog(
        SimpleNamespace(
            settings=SimpleNamespace(
                badapple_cache_path=cache_file(tmp_path),
                badapple_fps=1,
            )
        )
    )
    ctx = context()
    ctx.channel.send.return_value = SimpleNamespace(edit=AsyncMock(side_effect=http_error(429)))
    await cog.badapple.callback(cog, ctx)
    assert "Discord could not accept" in ctx.send.call_args.args[0]
    assert cog.player.task is None
    async with cog.player.reserve(5, 8):
        await cog.badapple.callback(cog, ctx)
    assert "already running" in ctx.send.call_args.args[0]


@pytest.mark.asyncio
async def test_six_fps_cache_and_playback(tmp_path, fast_clock):
    frames = [chr(0x2800 + index) for index in range(18)]
    animation = load_animation(cache_file(tmp_path, frames, fps=6, duration=3))
    player = BadApplePlayer()
    message = SimpleNamespace(edit=AsyncMock())
    async with player.reserve(1, 2):
        result = await player.play(message, animation, 6)
    assert result.target_fps == 6
    assert result.actual_fps == pytest.approx(6)
    assert result.seconds == pytest.approx(3)
    assert message.edit.await_count == 19
    with pytest.raises(ValueError, match="between 0.1 and 6"):
        await player.play(message, animation, 6.01)


def test_six_fps_setting():
    from bot.config.settings import Settings

    settings = Settings(
        _env_file=None,
        DISCORD_TOKEN="test-token",
        DATABASE_URL="postgresql+asyncpg://test:test@localhost/test",
        REDIS_URL="redis://localhost:6379/15",
        BADAPPLE_FPS=6,
    )
    assert settings.badapple_fps == 6


@pytest.mark.asyncio
async def test_slow_edit_backs_off_without_burst_or_skipping(fast_clock, caplog):
    player = BadApplePlayer()
    animation = Animation(1, 1, 3, 4 / 3, ("\u2800", "\u28ff", "\u2801", "\u2802"))
    starts = []

    async def edit(**kwargs):
        starts.append(fast_clock.now)
        if len(starts) == 2:
            fast_clock.now += 4  # Simulate an internal Discord rate-limit wait.

    message = SimpleNamespace(edit=AsyncMock(side_effect=edit))
    async with player.reserve(1, 2):
        result = await player.play(message, animation, 3)
    assert starts[:4] == pytest.approx([0, 1 / 3, 5 + 1 / 3, 6 + 1 / 3])
    assert result.frames == 4 and result.target_fps == 3
    assert result.actual_fps < 1
    assert "actual" in message.edit.call_args_list[2].kwargs["content"]
    assert [
        call.kwargs["content"].split("\n")[1] for call in message.edit.call_args_list[:4]
    ] == list(animation.frames)
    assert "badapple_slow_edit" in caplog.text


@pytest.mark.asyncio
async def test_slow_edit_logs_are_bounded_and_low_target_is_preserved(fast_clock, caplog):
    player = BadApplePlayer()
    animation = Animation(1, 1, 1, 3, ("\u2800",) * 3)
    starts = []

    async def edit(**kwargs):
        starts.append(fast_clock.now)
        fast_clock.now += 5

    message = SimpleNamespace(edit=AsyncMock(side_effect=edit))
    async with player.reserve(1, 2):
        await player.play(message, animation, 0.5)
    assert starts[:3] == [0, 7, 14]
    assert caplog.text.count("badapple_slow_edit") == 1
