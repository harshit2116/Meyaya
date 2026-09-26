"""Render a local ship layout preview with placeholder portraits."""

from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw
from bot.services.ship_card import render_ship_card


def portrait(background, hair):
    image = Image.new("RGB", (256, 256), background)
    draw = ImageDraw.Draw(image)
    draw.ellipse((52, 32, 204, 214), fill=hair)
    draw.ellipse((82, 75, 174, 184), fill="#f3c6b7")
    draw.rounded_rectangle((88, 116, 108, 123), radius=3, fill="#483444")
    draw.rounded_rectangle((148, 116, 168, 123), radius=3, fill="#483444")
    draw.arc((108, 137, 148, 162), 0, 180, fill="#b66d79", width=3)
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


if __name__ == "__main__":
    output = Path("logs/ship-preview.png")
    output.parent.mkdir(exist_ok=True)
    output.write_bytes(
        render_ship_card(
            portrait("#b67791", "#633b62"),
            portrait("#7388a4", "#323a53"),
            "Haru",
            "Ruru",
            88,
            "Dangerously compatible 💘",
        )
    )
    print(output.resolve())
    besties = output.with_name("besties-preview.png")
    besties.write_bytes(render_ship_card(
        portrait("#b67791", "#633b62"), portrait("#7388a4", "#323a53"),
        "Haru", "Ruru", 92, "Certified partners in chaos", theme="besties"
    ))
    print(besties.resolve())
