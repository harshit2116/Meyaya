"""Compact, locally rendered romance cards."""

from io import BytesIO
import math
import unicodedata

from PIL import Image, ImageDraw, ImageOps
from bot.services.card_renderer import font


def centered(draw, text, x, y, width, size, color):
    text = " ".join(text.split())
    while size > 16 and draw.textlength(text, font=font(size)) > width:
        size -= 1
    if draw.textlength(text, font=font(size)) > width:
        while text and draw.textlength(text + "…", font=font(size)) > width:
            text = text[:-1]
        text += "…"
    draw.text((x, y), text, font=font(size), fill=color, anchor="mm")


def render_ship_card(
    first, second, name_one, name_two, percentage=50, verdict="A cute little maybe", *, theme="ship"
):
    image = Image.new("RGB", (960, 520), "#170f22")
    draw = ImageDraw.Draw(image)
    for y in range(520):
        t = y / 519
        draw.line((0, y, 960, y), fill=(int(26 + 20 * t), int(15 + 8 * t), int(36 + 13 * t)))
    besties = theme == "besties"
    pink, pale, muted = ("#b6a4fa" if besties else "#f694b9"), "#fff0f5", "#c2a9bd"
    draw.rounded_rectangle(
        (16, 16, 944, 504), radius=26, fill="#1b1426", outline="#79516c", width=2
    )
    draw.text(
        (42, 41),
        "MEYAYA / THE BESTIE CLUB" if besties else "MEYAYA / THE LOVE LETTER",
        font=font(16),
        fill=pink,
    )
    draw.line((42, 76, 918, 76), fill="#483044")
    centered(
        draw,
        "SHARED SECRETS, MATCHING CHAOS" if besties else "A LITTLE CHEMISTRY, A LITTLE CHAOS",
        480,
        98,
        450,
        13,
        muted,
    )

    for data, name, cx in ((first, name_one, 204), (second, name_two, 756)):
        draw.ellipse((cx - 116, 119, cx + 116, 351), outline="#553347", width=1)
        draw.ellipse((cx - 109, 126, cx + 109, 344), fill=pink)
        with Image.open(BytesIO(data)) as source:
            if source.width * source.height > 4_000_000:
                raise ValueError("Avatar is too large")
            avatar = ImageOps.fit(
                source.convert("RGBA"), (208, 208), method=Image.Resampling.LANCZOS
            )
        mask = Image.new("L", (208, 208))
        ImageDraw.Draw(mask).ellipse((0, 0, 207, 207), fill=255)
        portrait = Image.new("RGBA", avatar.size, "#291e31")
        portrait.alpha_composite(avatar)
        image.paste(portrait.convert("RGB"), (cx - 104, 131), mask)
        draw.rounded_rectangle((cx - 147, 359, cx + 147, 406), radius=16, fill="#302036")
        centered(draw, name, cx, 382, 270, 25, pale)

    # Supersample only this small icon: rounded joins and antialiased edges
    # without multiplying the memory footprint of the entire card.
    scale = 4
    mask = Image.new("L", (128 * scale, 128 * scale))
    heart_draw = ImageDraw.Draw(mask)
    points = []
    for step in range(160):
        t = step * math.tau / 160
        points.append(
            (
                (64 + 3.0 * 16 * math.sin(t) ** 3) * scale,
                (
                    54
                    - 3.0
                    * (
                        13 * math.cos(t)
                        - 5 * math.cos(2 * t)
                        - 2 * math.cos(3 * t)
                        - math.cos(4 * t)
                    )
                )
                * scale,
            )
        )
    heart_draw.polygon(points, fill=255)
    heart_draw.line(points + [points[0]], fill=255, width=4 * scale, joint="curve")
    mask = mask.resize((128, 128), Image.Resampling.LANCZOS)
    image.paste("#aa91ef" if besties else "#ed719d", (416, 121, 544, 249), mask)
    draw.line((330, 184, 403, 184), fill="#79516c", width=2)
    draw.line((557, 184, 630, 184), fill="#79516c", width=2)
    centered(draw, f"{percentage}%", 480, 278, 230, 66, pale)
    centered(draw, "BESTIE ENERGY" if besties else "COMPATIBILITY", 480, 324, 220, 14, muted)
    for index in range(10):
        x = 381 + index * 20
        draw.rounded_rectangle(
            (x, 352, x + 15, 359),
            radius=3,
            fill=pink if index < round(percentage / 10) else "#493144",
        )
    draw.rounded_rectangle((42, 426, 918, 481), radius=17, fill="#352136")
    # Verdicts already carry emoji; the drawn heart supplies the visual accent.
    clean = "".join(c for c in verdict if unicodedata.category(c) not in {"So", "Mn", "Cf"}).strip()
    centered(draw, clean, 480, 454, 830, 25, pale)
    output = BytesIO()
    image.save(output, "PNG", compress_level=4)
    return output.getvalue()
