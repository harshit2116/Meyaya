"""Personalize the supplied duck animation in the shared, bounded image worker."""

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from bot.services.card_renderer import font

TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "duck" / "eject.gif"
CROP = (80, 22, 342, 240)  # Omit the recording's player list and microphone UI.
OUTPUT_SIZE = (480, 400)
MAX_OUTPUT_BYTES = 7 * 1024 * 1024


def duck_message(name):
    name = " ".join(str(name).split())[:32] or "Member"
    return f"{name} is looking for Davey Jones locker."


def _avatar(data, name):
    art = Image.new("RGB", (42, 42), "#344f6f")
    draw = ImageDraw.Draw(art)
    draw.text((21, 21), name[:1].upper() or "?", font=font(22), fill="white", anchor="mm")
    if data and len(data) <= 1024 * 1024:
        try:
            with Image.open(BytesIO(data)) as source:
                if source.width * source.height <= 4_000_000:
                    source.thumbnail((128, 128))
                    art = ImageOps.fit(source.convert("RGB"), (42, 42))
        except (OSError, ValueError):
            pass
    mask = Image.new("L", art.size)
    ImageDraw.Draw(mask).ellipse((0, 0, 41, 41), fill=255)
    return art, mask


def render_duck(name, avatar=b""):
    """Keep every source frame and fit the complete caption on one output line."""
    name = " ".join(str(name).split())[:32] or "Member"
    message = duck_message(name)
    # Measure the final sentence once, not each partial typewriter reveal. This
    # keeps font size stable throughout the animation and never wraps the ending.
    caption_font = fitted_caption_font(message)
    art, mask = _avatar(avatar, name)
    frames, durations = [], []
    with Image.open(TEMPLATE) as source:
        if source.size != (426, 240) or source.n_frames != 94:
            raise ValueError("Unsupported duck animation template")
        clean = source.convert("RGB").crop((48, 94, 383, 152))
        # One shared palette keeps dark ocean gradients and the portrait readable
        # without running an expensive colour quantizer on all 94 frames.
        swatch = source.convert("RGB").resize((128, 128))
        swatch.paste(art, (0, 86))
        palette = swatch.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
        for index in range(94):
            source.seek(index)
            duration = max(20, min(250, int(source.info.get("duration", 70))))
            frame = source.convert("RGB")
            if index >= 48:
                frame.paste(clean, (48, 94))
            draw = ImageDraw.Draw(frame)
            # Follow the duck's trajectory in this fixed source template.
            center_y = round((index - 24) * 6.2)
            if 18 <= index <= 64:
                frame.paste(art, (197, center_y - 21), mask)
                draw.ellipse((196, center_y - 22, 239, center_y + 21), outline="#d6e9ff", width=1)
            rendered = frame.crop(CROP).resize(OUTPUT_SIZE, Image.Resampling.LANCZOS)
            if index >= 48:
                visible = message[:round(len(message) * min(1, (index - 46) / 30))]
                ImageDraw.Draw(rendered).text(
                    (OUTPUT_SIZE[0] // 2, round((122 - CROP[1]) * OUTPUT_SIZE[1] / (CROP[3] - CROP[1]))),
                    visible, font=caption_font, fill="white", anchor="mm",
                    stroke_width=1, stroke_fill="#101929",
                )
            frames.append(rendered.quantize(palette=palette, dither=Image.Dither.NONE))
            durations.append(duration)
    output = BytesIO()
    frames[0].save(output, format="GIF", save_all=True, append_images=frames[1:],
                   duration=durations, loop=0, disposal=2, optimize=False)
    data = output.getvalue()
    if len(data) > MAX_OUTPUT_BYTES:
        raise ValueError("Duck animation exceeds attachment budget")
    return data


def fitted_caption_font(message):
    """Fit text at final resolution with comfortable margins and its outline."""
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for size in range(20, 0, -1):
        candidate = font(size)
        box = draw.textbbox((0, 0), message, font=candidate, stroke_width=1)
        if box[2] - box[0] <= OUTPUT_SIZE[0] - 32:
            return candidate
    return font(1)
