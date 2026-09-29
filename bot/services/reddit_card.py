"""Bounded, local Reddit-style parody card. No web or AI dependencies."""

from io import BytesIO
import re

from PIL import Image, ImageDraw, ImageOps

from bot.services.card_renderer import font, label, lines

BACKGROUND = "#0e1113"
INK = "#eef1f3"
MUTED = "#8ba2ad"
PILL = "#272f33"


def _portrait(image, draw, data, x, y, size, initials):
    draw.ellipse((x, y, x + size, y + size), fill=PILL)
    draw.text((x + size / 2, y + size / 2), initials, font=font(18), fill=INK, anchor="mm")
    if not data or len(data) > 1024 * 1024:
        return
    try:
        with Image.open(BytesIO(data)) as source:
            if source.width * source.height > 4_000_000:
                return
            source.thumbnail((128, 128))
            art = ImageOps.fit(source.convert("RGB"), (size, size))
        mask = Image.new("L", (size, size))
        ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
        image.paste(art, (x, y), mask)
    except (OSError, ValueError):
        pass


def _arrow(draw, x, y, *, down=False):
    points = [(x, y + 8), (x + 7, y), (x + 14, y + 8), (x + 10, y + 8),
              (x + 10, y + 16), (x + 4, y + 16), (x + 4, y + 8), (x, y + 8)]
    if down:
        points = [(px, y + 16 - (py - y)) for px, py in points]
    draw.line(points, fill=INK, width=2)


def _count(value):
    return f"{value / 1000:.1f}K" if value >= 1000 else str(value)


def render_reddit(server, username, post, comment="", author_avatar=b"", meyaya_avatar=b"", votes=3200, replies=1900):
    # Bound every text input even when called outside the command.
    server = re.sub(r"\s+", "-", str(server).strip())[:60] or "server"
    username = " ".join(str(username).split())[:50]
    post = " ".join(str(post).split())[:300]
    comment = " ".join(str(comment).split())[:240]
    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    post_rows = lines(measure, post, 25, 600)
    comment_rows = lines(measure, comment, 22, 546) if comment else []
    body_y = 104
    pills_y = body_y + len(post_rows) * 33 + 26
    divider_y = pills_y + 68
    height = divider_y + (107 + len(comment_rows) * 30 if comment else 22) + 16
    image = Image.new("RGB", (660, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    _portrait(image, draw, author_avatar, 26, 27, 52, "U")
    label(draw, (92, 29, 480, 27), f"r/{server}", 20, INK)
    label(draw, (92, 58, 480, 25), f"u/{username}  /  just now", 17, MUTED)
    draw.text((614, 39), "...", font=font(22), fill=MUTED)
    label(draw, (28, body_y, 600, len(post_rows) * 33), post, 25, INK)
    draw.rounded_rectangle((28, pills_y, 159, pills_y + 39), radius=20, fill=PILL)
    _arrow(draw, 40, pills_y + 11)
    draw.text((65, pills_y + 9), _count(votes), font=font(17), fill=INK)
    _arrow(draw, 130, pills_y + 11, down=True)
    draw.rounded_rectangle((172, pills_y, 284, pills_y + 39), radius=20, fill=PILL)
    draw.rounded_rectangle((186, pills_y + 10, 203, pills_y + 25), radius=5, outline=INK, width=2)
    draw.line((188, pills_y + 24, 186, pills_y + 29, 193, pills_y + 25), fill=INK, width=2)
    draw.text((215, pills_y + 9), _count(replies) if comment else "0", font=font(17), fill=INK)
    draw.rounded_rectangle((297, pills_y, 394, pills_y + 39), radius=20, fill=PILL)
    draw.text((318, pills_y + 9), "Share", font=font(17), fill=INK)
    draw.line((28, divider_y, 632, divider_y), fill="#303a40", width=1)
    if comment:
        draw.text((28, divider_y + 18), "Top comment", font=font(16), fill=MUTED)
        y = divider_y + 54
        _portrait(image, draw, meyaya_avatar, 28, y, 35, "M")
        draw.text((78, y + 3), "u/Meyaya", font=font(19), fill=INK)
        draw.text((192, y + 5), "just now", font=font(16), fill=MUTED)
        label(draw, (78, y + 43, 546, len(comment_rows) * 30), comment, 22, "#bfd7e4")
    output = BytesIO()
    image.save(output, format="PNG", compress_level=1)
    return output.getvalue()
