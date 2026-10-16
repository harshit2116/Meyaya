"""Build the authored clash cinematics offline. No network or bot credentials.

Run from the repository root with the two original GIFs as positional inputs.
The shorter introduction loops at its original speed alongside the longer clip.
"""
import argparse
from bisect import bisect_right
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps
from bot.services.card_renderer import font

ASSETS = Path(__file__).resolve().parents[1] / "bot/assets/duels"
SCENES = {
    "arena": "clash-arena-v3.png",
    "worldfall": "clash-worldfall-v3.png",
    "cascade": "meyaya-battle-v3.png",
    "sever": "veyra-battle-v3.png",
    "genesis": "clash-origin-v3.png",
    "dominion": "clash-erasure-v3.png",
    "dawn": "clash-origin-v3.png",
    "erasure": "clash-erasure-v3.png",
    "origin-win": "clash-origin-win-v3.png",
    "erasure-win": "clash-erasure-win-v3.png",
}
ATTACKS = ("cascade", "sever", "genesis", "dominion", "dawn", "erasure")


def load_clip(path):
    frames, ends, elapsed = [], [], 0
    with Image.open(path) as source:
        if source.n_frames > 400 or source.width * source.height > 4_000_000:
            raise ValueError("Introduction exceeds the offline decode budget")
        for index in range(source.n_frames):
            source.seek(index)
            frame = ImageOps.contain(source.convert("RGB"), (400, 225), Image.Resampling.LANCZOS)
            frames.append(frame)
            elapsed += max(20, source.info.get("duration", 80))
            ends.append(elapsed)
    if len(frames) < 2:
        raise ValueError("Opening source must be animated")
    return frames, ends


def combined_intro(left_path, right_path):
    left, left_ends = load_clip(left_path)
    right, right_ends = load_clip(right_path)
    # 10 fps, at most 10 seconds, with both original timelines preserved.
    duration = min(10_000, max(left_ends[-1], right_ends[-1]))
    output = []
    for time in range(0, duration, 100):
        canvas = Image.new("RGB", (800, 300), "#100d19")
        for x, frames, ends in ((0, left, left_ends), (400, right, right_ends)):
            frame = frames[bisect_right(ends, time % ends[-1])]
            canvas.paste(frame, (x + (400-frame.width)//2, 38 + (225-frame.height)//2))
        draw = ImageDraw.Draw(canvas)
        draw.text((18, 8), "MEYAYA / ORIGIN", font=font(17), fill="#f3b2dc")
        draw.text((420, 8), "VEYRA / ERASURE", font=font(17), fill="#ff617e")
        draw.line((399, 0, 399, 300), fill="#c4a7ee", width=2)
        draw.text((400, 277), "TWO AUTHORITIES. ONE WORLD.", font=font(14),
                  anchor="mm", fill="#e7dcf4")
        output.append(canvas.resize((640, 240), Image.Resampling.LANCZOS))
        canvas.close()
    samples = Image.new("RGB", (640, 240 * 8))
    for index in range(8):
        samples.paste(output[index * (len(output)-1)//7], (0, index*240))
    palette = samples.quantize(colors=128)
    encoded = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in output]
    encoded[0].save(ASSETS / "clash-opening-v3.gif", save_all=True,
                   append_images=encoded[1:], duration=100, loop=0, optimize=True)
    samples.close()
    palette.close()
    for frame in left + right + output + encoded:
        frame.close()


def build_scenes(keys=None):
    for key, filename in SCENES.items():
        if keys is not None and key not in keys:
            continue
        with Image.open(ASSETS / filename) as source:
            base = ImageOps.pad(source.convert("RGB"), (960, 420), color="#100d19")
        base.save(ASSETS / f"clash-{key}-v3.jpg", quality=85)
        if key in ATTACKS:
            small = base.resize((640, 280), Image.Resampling.LANCZOS)
            palette = small.quantize(colors=96)
            frames = []
            origin = key in {"cascade", "genesis", "dawn"}
            for tick in range(16):
                # Localized particles preserve GIF delta compression and the faces.
                frame = small.copy()
                draw = ImageDraw.Draw(frame, "RGBA")
                for i in range(14):
                    x, y = (i * 47 + tick * (3 if origin else -4)) % 640, 240 + (i*7) % 30
                    if origin:
                        draw.ellipse((x, y, x+8, y+4), fill=(245, 170, 224, 200))
                    else:
                        draw.line((x, y, x+18, y-5), fill=(240, 60, 106, 190), width=2)
                frames.append(frame.quantize(palette=palette, dither=Image.Dither.NONE))
                frame.close()
            frames[0].save(ASSETS / f"clash-{key}-v3.gif", save_all=True,
                           append_images=frames[1:], duration=150, loop=1, optimize=True)
            for frame in frames:
                frame.close()
            small.close()
            palette.close()
        base.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("meyaya_intro", type=Path)
    parser.add_argument("veyra_intro", type=Path)
    args = parser.parse_args()
    combined_intro(args.meyaya_intro, args.veyra_intro)
    build_scenes()
    for path in sorted(ASSETS.glob("clash-*-v3.gif")):
        if path.stat().st_size > 7_000_000:
            raise ValueError(f"{path.name} exceeds cinematic upload budget")
        with Image.open(path) as im:
            print(path.name, im.size, im.n_frames, path.stat().st_size, "bytes")

