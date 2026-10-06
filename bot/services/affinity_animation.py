"""Soft, colour-matched environments for the illustrated awakening cores."""

from io import BytesIO
import math
from random import Random

from PIL import Image, ImageDraw, ImageFilter

from bot.data.fantasy import AFFINITIES
from bot.services.card_renderer import font
from bot.services.fantasy_awaken_art import affinity_sprite

SIZE = (560, 280)


def crystal_colors(art, theme):
    if art is None:
        return tuple(bytes.fromhex(theme.color[1:])), (180, 167, 220)
    # Ignore the transparent canvas and neutral metal; sample the actual magic.
    sample = Image.new("RGB", art.size)
    sample.paste(art, (0, 0), art)
    colors = sample.quantize(colors=24).convert("RGB").getcolors(art.width * art.height)
    colors = [
        (count, color)
        for count, color in colors
        if max(color) > 85 and max(color) - min(color) > 35
    ]
    colors.sort(key=lambda item: item[0] * (max(item[1]) - min(item[1])), reverse=True)
    if not colors:
        return tuple(bytes.fromhex(theme.color[1:])), (180, 167, 220)
    primary = colors[0][1]
    secondary = next(
        (color for _, color in colors[1:] if sum(abs(a - b) for a, b in zip(primary, color)) > 100),
        primary,
    )
    return primary, secondary


def atmosphere(primary, secondary):
    # Smooth sampled light rather than a flat themed panel or a visible halo disc.
    small = Image.new("RGB", (140, 70))
    pixels = []
    for y in range(70):
        for x in range(140):
            core = math.exp(-(((x - 70) / 34) ** 2 + ((y - 27) / 23) ** 2))
            veil = math.exp(-(((x - 88) / 48) ** 2 + ((y - 30) / 16) ** 2))
            pixels.append(
                tuple(
                    round(5 + p * (0.025 + core * 0.105) + s * veil * 0.025)
                    for p, s in zip(primary, secondary)
                )
            )
    small.putdata(pixels)
    return small.resize(SIZE, Image.Resampling.BICUBIC)


def render_affinity_ritual(profile):
    key = profile.affinity_id
    theme = AFFINITIES.get(key, AFFINITIES["arcane"])
    art = affinity_sprite(key)
    primary, secondary = crystal_colors(art, theme)
    base = atmosphere(primary, secondary).convert("RGBA")
    caption = tuple(round(c * 0.40 + 235 * 0.60) for c in primary)
    trim = tuple(round(c * 0.20 + 16) for c in secondary)
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
        fill=tuple(round(c * 0.55) for c in caption),
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
    images = []
    for index in range(24):
        phase = math.tau * index / 24
        frame = base.copy()
        layer = Image.new("RGBA", SIZE)
        draw = ImageDraw.Draw(layer)
        for x, y, offset, radius in orbs:
            horizontal = x + math.sin(phase + offset) * 9
            vertical = y + math.cos(phase + offset) * 12
            # Constant brightness: only background position moves.
            draw.ellipse(
                (horizontal - radius, vertical - radius, horizontal + radius, vertical + radius),
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
