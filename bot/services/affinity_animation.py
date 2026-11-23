"""Soft, colour-matched environments for the illustrated awakening cores."""

from __future__ import annotations

from io import BytesIO
import math
from random import Random
from typing import Any

from PIL import Image, ImageDraw, ImageFilter

from bot.data.fantasy import AFFINITIES, Affinity
from bot.services.card_renderer import font
from bot.services.fantasy_awaken_art import affinity_sprite

type RGB = tuple[int, int, int]

SIZE = (560, 280)


def _hex_rgb(code: str) -> RGB:
    raw = bytes.fromhex(code[1:])
    return (raw[0], raw[1], raw[2])


def crystal_colors(art: Image.Image | None, theme: Affinity) -> tuple[RGB, RGB]:
    if art is None:
        return _hex_rgb(theme.color), (180, 167, 220)
    # Ignore the transparent canvas and neutral metal; sample the actual magic.
    sample = Image.new("RGB", art.size)
    sample.paste(art, (0, 0), art)
    raw_colors = sample.quantize(colors=24).convert("RGB").getcolors(art.width * art.height) or []
    colors: list[tuple[int, RGB]] = []
    for count, color in raw_colors:
        if isinstance(color, tuple) and len(color) == 3:
            rgb: RGB = (int(color[0]), int(color[1]), int(color[2]))
            if max(rgb) > 85 and max(rgb) - min(rgb) > 35:
                colors.append((count, rgb))
    colors.sort(key=lambda item: item[0] * (max(item[1]) - min(item[1])), reverse=True)
    if not colors:
        return _hex_rgb(theme.color), (180, 167, 220)
    primary = colors[0][1]
    secondary = next(
        (color for _, color in colors[1:] if sum(abs(a - b) for a, b in zip(primary, color, strict=True)) > 100),
        primary,
    )
    return primary, secondary


def atmosphere(primary: RGB, secondary: RGB) -> Image.Image:
    # Smooth sampled light rather than a flat themed panel or a visible halo disc.
    small = Image.new("RGB", (140, 70))
    pixels: list[RGB] = []
    for y in range(70):
        for x in range(140):
            core = math.exp(-(((x - 70) / 34) ** 2 + ((y - 27) / 23) ** 2))
            veil = math.exp(-(((x - 88) / 48) ** 2 + ((y - 30) / 16) ** 2))
            pixels.append(
                (
                    round(5 + primary[0] * (0.025 + core * 0.105) + secondary[0] * veil * 0.025),
                    round(5 + primary[1] * (0.025 + core * 0.105) + secondary[1] * veil * 0.025),
                    round(5 + primary[2] * (0.025 + core * 0.105) + secondary[2] * veil * 0.025),
                )
            )
    small.putdata(pixels)
    return small.resize(SIZE, Image.Resampling.BICUBIC)


def render_affinity_ritual(profile: Any) -> bytes:
    key = profile.affinity_id
    theme = AFFINITIES.get(key, AFFINITIES["arcane"])
    art = affinity_sprite(key)
    primary, secondary = crystal_colors(art, theme)
    base = atmosphere(primary, secondary).convert("RGBA")
    caption: RGB = (
        round(primary[0] * 0.40 + 235 * 0.60),
        round(primary[1] * 0.40 + 235 * 0.60),
        round(primary[2] * 0.40 + 235 * 0.60),
    )
    trim: RGB = (
        round(secondary[0] * 0.20 + 16),
        round(secondary[1] * 0.20 + 16),
        round(secondary[2] * 0.20 + 16),
    )
    draw = ImageDraw.Draw(base)
    # Quiet corners and a small caption divider leave the crystal in focus.
    for x, direction in ((18, 1), (541, -1)):
        for y, vertical in ((18, 1), (261, -1)):
            draw.line((x, y + vertical * 10, x, y, x + direction * 20, y), fill=trim)
    draw.text((280, 232), theme.name.upper(), font=font(20), fill=caption, anchor="mm")
    draw.text(
        (280, 254),
        "A DORMANT SIGNATURE ANSWERS",
        font=font(11),
        fill=(round(caption[0] * 0.55), round(caption[1] * 0.55), round(caption[2] * 0.55)),
        anchor="mm",
    )
    draw.line((223, 215, 337, 215), fill=trim)
    if art is not None:
        position = (280 - art.width // 2, 110 - art.height // 2)
        light = Image.new("RGBA", art.size, (*primary, 0))
        light.putalpha(art.getchannel("A").point(lambda value: round(value * 0.13)))
        base.alpha_composite(light.filter(ImageFilter.GaussianBlur(14)), position)
        base.alpha_composite(art, position)
    else:
        from bot.services.fantasy_render import glyph

        glyph(ImageDraw.Draw(base), (280, 110), 40, theme.motif, caption, 2)
    rng = Random(key)
    orbs = [
        (
            rng.uniform(46, 148) if index % 2 else rng.uniform(412, 514),
            rng.uniform(44, 182),
            rng.uniform(0, math.tau),
            rng.uniform(3, 8),
        )
        for index in range(10)
    ]
    images: list[Image.Image] = []
    for index in range(24):
        phase = math.tau * index / 24
        frame = base.copy()
        layer = Image.new("RGBA", SIZE)
        draw = ImageDraw.Draw(layer)
        for ox, oy, offset, radius in orbs:
            horizontal = ox + math.sin(phase + offset) * 9
            orb_y = oy + math.cos(phase + offset) * 12
            # Constant brightness: only background position moves.
            draw.ellipse(
                (horizontal - radius, orb_y - radius, horizontal + radius, orb_y + radius),
                fill=(*primary, 45),
                outline=(*primary, 70),
                width=1,
            )
        frame = Image.alpha_composite(frame, layer.filter(ImageFilter.GaussianBlur(2)))
        images.append(frame.convert("RGB"))
    # One shared 256-colour palette preserves the crystal and smooth dark gradients.
    sample = Image.new("RGB", (560 * 3, 280))
    for column, index in enumerate((0, 6, 12)):
        sample.paste(images[index], (column * 560, 0))
    palette = sample.quantize(colors=256)
    frames = [
        image.quantize(palette=palette, dither=Image.Dither.FLOYDSTEINBERG) for image in images
    ]
    # Freeze the crystal's indexed pixels too; background dithering must not
    # make its fine facets shimmer from frame to frame.
    core_box = (188, 12, 372, 208)
    fixed_core = (
        base.convert("RGB")
        .quantize(palette=palette, dither=Image.Dither.FLOYDSTEINBERG)
        .crop(core_box)
    )
    for frame in frames:
        frame.paste(fixed_core, core_box)
    output = BytesIO()
    frames[0].save(
        output,
        "GIF",
        save_all=True,
        append_images=frames[1:],
        duration=100,
        loop=0,
        disposal=1,
        optimize=True,
    )
    if output.tell() > 1024 * 1024:
        raise ValueError("Affinity animation exceeds upload budget")
    return output.getvalue()
