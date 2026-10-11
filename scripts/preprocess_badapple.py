"""Offline, local-only full-video conversion. Run with python -m scripts.preprocess_badapple."""

from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import subprocess
import tempfile
import threading
from fractions import Fraction
from pathlib import Path

from PIL import Image

from bot.utils.badapple import (
    DEFAULT_CACHE,
    MAX_CHARACTERS,
    MAX_FRAMES,
    MediaError,
    image_to_braille,
    load_animation,
    validate_metadata,
)


def probe_video(source: Path, ffprobe: str) -> tuple[float, float]:
    if not source.is_file() or source.stat().st_size == 0:
        raise MediaError("Source video is missing or empty; supply a local video file.")
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-select_streams",
                "v:0",
                "-show_entries",
                (
                    "stream=width,height,avg_frame_rate,duration,sample_aspect_ratio:"
                    "stream_side_data=rotation:format=duration"
                ),
                "-of",
                "json",
                str(source.resolve()),
            ],
            capture_output=True,
            check=True,
            timeout=30,
        )
        metadata = json.loads(result.stdout)
        stream = metadata["streams"][0]
        width, height = int(stream["width"]), int(stream["height"])
        source_fps = float(Fraction(stream["avg_frame_rate"]))
        duration = float(stream.get("duration") or metadata.get("format", {}).get("duration", 0))
        sar_text = stream.get("sample_aspect_ratio", "1:1")
        sar = float(Fraction(sar_text.replace(":", "/"))) if sar_text != "N/A" else 1.0
        if (
            min(width, height) <= 0
            or width * height > 33_177_600
            or not 0 < source_fps <= 240
            or not 0 < duration <= 3600
            or not 0 < sar <= 100
        ):
            raise MediaError("Invalid video dimensions, frame rate, aspect ratio or duration.")
        if any(item.get("rotation", 0) % 360 for item in stream.get("side_data_list", [])):
            raise MediaError("Normalize the video's rotation before preprocessing.")
        return duration, width * sar / height
    except FileNotFoundError as exc:
        raise MediaError("ffprobe is unavailable; install FFmpeg or pass --ffprobe.") from exc
    except (
        subprocess.SubprocessError,
        OSError,
        ValueError,
        KeyError,
        IndexError,
        TypeError,
        ZeroDivisionError,
    ) as exc:
        if isinstance(exc, MediaError):
            raise
        raise MediaError("Cannot read video metadata; source is corrupt or unsupported.") from exc


def preprocess(
    source: Path,
    output: Path = DEFAULT_CACHE,
    *,
    width: int = 48,
    height: int | None = None,
    fps: float = 1.0,
    threshold: int = 128,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
    overwrite: bool = False,
    timeout: float = 600,
) -> tuple[int, float]:
    source, output = source.resolve(), output.resolve()
    if source == output or output.suffix != ".gz" or output.is_dir():
        raise MediaError("Output must be a .gz file different from the source video.")
    if output.exists() and not overwrite:
        raise MediaError("Output already exists; use --overwrite to replace it atomically.")
    if not math.isfinite(timeout) or not 1 <= timeout <= 3600:
        raise MediaError("Conversion timeout must be between 1 and 3600 seconds.")
    if type(threshold) is not int or not 0 <= threshold <= 255:
        raise MediaError("Threshold must be an integer from 0 to 255.")
    duration, aspect = probe_video(source, ffprobe)
    height = max(1, round(width * 0.5 / aspect)) if height is None else height
    header = {"version": 1, "width": width, "height": height, "fps": fps, "duration": duration}
    validate_metadata(header)
    # Scale using display aspect ratio, including non-square source pixels.
    pixel_width, pixel_height = width * 2, height * 4
    fitted_width = max(1, min(pixel_width, round(pixel_height * aspect)))
    fitted_height = max(1, min(pixel_height, round(pixel_width / aspect)))
    frame_bytes = fitted_width * fitted_height
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".tmp", delete=False) as raw:
            temporary = Path(raw.name)
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as cache:

                def write_record(record: object) -> None:
                    cache.write(
                        (
                            json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
                        ).encode("utf-8")
                    )

                write_record(header)
                with tempfile.TemporaryFile() as errors:
                    try:
                        process = subprocess.Popen(
                            [
                                ffmpeg,
                                "-nostdin",
                                "-v",
                                "fatal",
                                "-xerror",
                                "-threads",
                                "1",
                                "-protocol_whitelist",
                                "file,pipe",
                                "-noautorotate",
                                "-i",
                                str(source),
                                "-map",
                                "0:v:0",
                                "-an",
                                "-sn",
                                "-dn",
                                "-filter_threads",
                                "1",
                                "-vf",
                                (
                                    f"setpts=PTS-STARTPTS,fps={fps}:start_time=0:round=up,"
                                    f"scale={fitted_width}:{fitted_height}:flags=lanczos,setsar=1"
                                ),
                                "-threads",
                                "1",
                                "-f",
                                "rawvideo",
                                "-pix_fmt",
                                "gray",
                                "pipe:1",
                            ],
                            stdout=subprocess.PIPE,
                            stderr=errors,
                        )
                    except FileNotFoundError as exc:
                        raise MediaError(
                            "ffmpeg is unavailable; install FFmpeg or pass --ffmpeg."
                        ) from exc
                    timer = threading.Timer(timeout, process.kill)
                    timer.daemon = True
                    timer.start()
                    count = characters = 0
                    try:
                        assert process.stdout is not None
                        while True:
                            pixels = process.stdout.read(frame_bytes)
                            if not pixels:
                                break
                            if len(pixels) != frame_bytes:
                                raise MediaError("Video decoder returned a truncated frame.")
                            with Image.frombytes(
                                "L", (fitted_width, fitted_height), pixels
                            ) as image:
                                frame = image_to_braille(image, width, height, threshold)
                            count += 1
                            characters += len(frame)
                            if count > MAX_FRAMES or characters > MAX_CHARACTERS:
                                raise MediaError("Decoded video exceeds the cache budget.")
                            write_record(frame)
                        if process.wait() != 0:
                            raise MediaError(
                                "Video decoding failed or timed out; cache was not replaced."
                            )
                    finally:
                        timer.cancel()
                        if process.poll() is None:
                            process.kill()
                        process.wait()
                        if process.stdout is not None:
                            process.stdout.close()
                write_record({"frames": count})
        # Validate EOF, duration coverage and content before publishing anything.
        load_animation(temporary)
        if output.exists() and not overwrite:
            raise MediaError("Output appeared during conversion; refusing to overwrite it.")
        os.replace(temporary, output)
        return count, duration
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Developer-supplied local video, never a URL")
    parser.add_argument("--output", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--width", type=int, default=48, help="Braille columns")
    parser.add_argument("--height", type=int, help="Braille rows; default preserves source aspect")
    parser.add_argument("--fps", type=float, default=1.0, help="Sampling FPS, 0.1 to 6")
    parser.add_argument("--threshold", type=int, default=128)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        count, duration = preprocess(**vars(args))
    except (MediaError, OSError) as exc:
        parser.exit(1, f"Preprocessing failed: {exc}\n")
    print(
        f"Source: {duration:.2f}s; expected approximately {math.ceil(duration * args.fps)} frames."
    )
    print(
        f"Saved all {count} sampled frames to {args.output} ({args.output.stat().st_size} bytes)."
    )
    print(
        f"At {args.fps:g} target FPS: at least {count / args.fps:.2f}s playback; "
        "set BADAPPLE_FPS to match. Discord delays can make playback longer."
    )


if __name__ == "__main__":
    main()
