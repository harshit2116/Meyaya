"""Bundled AI illustrations, composed locally with saved identity metadata."""

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageOps

from bot.data.fantasy import AFFINITIES, RARITY_COLORS, WEAPONS

ART_DIR = Path(__file__).resolve().parents[1] / "assets" / "awakening"


@lru_cache(maxsize=48)
def asset_sprite(filename, size):
    """Cache only immutable source sprites; callers receive their own copy."""
    try:
        with Image.open(ART_DIR / filename) as source:
            art = source.convert("RGBA")
            art.thumbnail((size - 16, size - 16), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (size, size))
        canvas.alpha_composite(art, ((size - art.width) // 2, (size - art.height) // 2))
        return canvas
    except (OSError, ValueError):
        return None


def weapon_sprite(family, design, accent, rarity, seed):
    """Name chooses the illustration; affinity, rarity and saved ID refine it."""
    names = WEAPONS.get(family, ("", ()))[1]
    if not names:
        return None
    name = names[design % len(names)].lower()
    source = asset_sprite(f"weapons/{family}-{name}.png", 260)
    if source is None:
        return None
    tier = RARITY_COLORS.index(rarity) if rarity in RARITY_COLORS else 0
    alpha = source.getchannel("A")
    metal = ImageEnhance.Color(source).enhance(0.25 + tier * 0.20)
    metal = ImageEnhance.Brightness(metal).enhance(0.82 + tier * 0.036)
    finish = ImageOps.colorize(ImageOps.grayscale(source), "#111322", rarity).convert("RGBA")
    metal = Image.blend(metal, finish, 0.10 + tier * 0.035)
    # Keep the painted metal detail while letting affinity colour its magic.
    shaded = ImageOps.colorize(ImageOps.grayscale(source), "#111322", accent).convert("RGBA")
    art = Image.blend(metal, shaded, 0.10 + tier * 0.025 + (seed % 31) / 1000)
    art.putalpha(alpha)
    draw = ImageDraw.Draw(art)
    # Higher tiers accumulate resonant gems. Full saved ID places them uniquely.
    for index in range(2 + tier * 3):
        x = 18 + (seed + index * 73) % 222
        y = 18 + (seed // 19 + index * 47) % 222
        if alpha.getpixel((x, y)) > 200:
            draw.ellipse((x - 1, y - 1, x + 1, y + 1), fill=rarity)
    return art


def affinity_sprite(affinity_id):
    if affinity_id not in AFFINITIES:
        return None
    source = asset_sprite(f"affinities/{affinity_id}.png", 174)
    return source.copy() if source is not None else None
