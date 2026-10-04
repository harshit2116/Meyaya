"""Local, supersampled weapon illustrations and a gentle acquisition animation."""

from io import BytesIO
import math

from PIL import Image, ImageDraw, ImageFilter

from bot.data.fantasy import RARITIES, RARITY_COLORS
from bot.services.card_renderer import font
from bot.services.fantasy_render import blend, rgb, theme_for

WEAPON_CARD_SIZE = (640, 420)
MAX_WEAPON_BYTES = 4 * 1024 * 1024


def weapon_art(family, accent, rarity):
    """Ten distinct silhouettes; no external downloads or AI requests."""
    image = Image.new("RGBA", (640, 640))
    draw = ImageDraw.Draw(image)

    def polygon(points, fill, outline=None):
        draw.polygon([(x * 2, y * 2) for x, y in points], fill=fill, outline=outline, width=3)

    def line(points, fill, width=3):
        draw.line([(x * 2, y * 2) for x, y in points], fill=fill, width=width * 2)

    def ellipse(box, fill, outline=None, width=2):
        draw.ellipse(tuple(v * 2 for v in box), fill=fill, outline=outline, width=width * 2)

    steel, shade, gold = "#edf2ff", "#7185ab", "#d8b87d"

    def blade(x, y, length=165, breadth=22, curved=False):
        polygon(
            [
                (x, y),
                (x + breadth, y + 32),
                (x + breadth - (10 if curved else 0), y + length),
                (x - breadth, y + length),
                (x - breadth, y + 32),
            ],
            steel,
            shade,
        )
        polygon(
            [(x, y + 5), (x, y + length), (x - breadth + 2, y + length), (x - breadth + 2, y + 33)],
            shade,
        )
        line([(x, y + 30), (x, y + length - 6)], accent, 2)
        polygon(
            [
                (x - 39, y + length),
                (x + 39, y + length),
                (x + 34, y + length + 10),
                (x - 34, y + length + 10),
            ],
            gold,
        )
        polygon(
            [
                (x - 8, y + length + 10),
                (x + 8, y + length + 10),
                (x + 8, y + length + 57),
                (x - 8, y + length + 57),
            ],
            "#35304e",
            gold,
        )
        for offset in range(18, 52, 8):
            line([(x - 7, y + length + offset), (x + 7, y + length + offset - 4)], gold, 1)
        ellipse((x - 10, y + length + 51, x + 10, y + length + 70), rarity, gold)

    if family in {"sword", "greatsword", "katana"}:
        blade(
            160,
            24,
            185 if family == "greatsword" else 165,
            32 if family == "greatsword" else 14 if family == "katana" else 22,
            curved=family == "katana",
        )
    elif family == "daggers":
        blade(106, 67, 110, 18)
        blade(214, 40, 110, 18)
    elif family == "spellbook":
        polygon(
            [
                (61, 73),
                (150, 61),
                (160, 74),
                (170, 61),
                (259, 73),
                (259, 255),
                (172, 243),
                (160, 251),
                (148, 243),
                (61, 255),
            ],
            "#493450",
            gold,
        )
        polygon([(72, 83), (149, 73), (154, 87), (154, 234), (72, 243)], "#eee2ce")
        polygon([(166, 87), (171, 73), (248, 83), (248, 243), (166, 234)], "#dacdbb")
        line([(160, 80), (160, 241)], gold, 4)
        for y in range(110, 215, 17):
            line([(84, y), (138, y - 4)], "#9e8193", 2)
            line([(181, y - 4), (234, y)], "#9e8193", 2)
        ellipse((187, 130, 224, 167), accent, gold)
    elif family == "bow":
        draw.arc((125 * 2, 36 * 2, 241 * 2, 282 * 2), -90, 90, fill=gold, width=12)
        line([(183, 36), (183, 282)], "#e4ddeb", 2)
        line([(71, 162), (251, 162)], shade, 5)
        polygon([(278, 162), (247, 148), (247, 176)], steel, gold)
        polygon([(71, 162), (91, 145), (113, 145), (98, 162), (113, 179), (91, 179)], accent)
        ellipse((219, 145, 235, 179), rarity, gold)
    else:
        # Staff, spear, axe and mace share a haft, not their distinctive heads.
        polygon([(151, 100), (169, 100), (168, 281), (152, 281)], "#40354b", gold)
        for y in range(186, 258, 12):
            line([(153, y), (167, y - 5)], gold, 2)
        ellipse((151, 275, 169, 293), rarity, gold)
        if family == "spear":
            polygon([(160, 17), (186, 99), (160, 121), (134, 99)], steel, gold)
            polygon([(160, 21), (160, 116), (138, 97)], shade)
            line([(160, 44), (160, 105)], accent, 3)
        elif family == "axe":
            polygon([(103, 37), (145, 54), (151, 99), (115, 120), (80, 96)], steel, gold)
            polygon([(217, 37), (175, 54), (169, 99), (205, 120), (240, 96)], steel, gold)
            ellipse((146, 53, 174, 104), rarity, gold)
        elif family == "mace":
            polygon(
                [
                    (160, 22),
                    (176, 44),
                    (197, 43),
                    (192, 66),
                    (209, 87),
                    (185, 99),
                    (174, 122),
                    (151, 117),
                    (126, 126),
                    (123, 103),
                    (105, 85),
                    (124, 68),
                    (126, 43),
                    (148, 45),
                ],
                shade,
                gold,
            )
            ellipse((134, 55, 186, 107), rarity, steel)
        else:
            ellipse((117, 28, 203, 114), None, gold, 5)
            polygon([(160, 33), (184, 70), (160, 107), (136, 70)], accent, steel)
            line([(160, 38), (160, 99)], "#fff3fa", 2)
    return image.resize((260, 260), Image.Resampling.LANCZOS)


def render_weapon_acquisition(profile):
    theme = theme_for(profile)
    dark, accent = rgb(theme.dark), rgb(theme.color)
    tier = RARITIES.index(profile.weapon_rarity) if profile.weapon_rarity in RARITIES else 0
    rarity = RARITY_COLORS[tier]
    base = Image.new("RGB", WEAPON_CARD_SIZE)
    draw = ImageDraw.Draw(base)
    for y in range(420):
        draw.line((0, y, 640, y), fill=blend(dark, accent, max(0, 1 - abs(y - 188) / 260) * 0.14))
    draw.rounded_rectangle((12, 12, 627, 407), radius=20, outline=blend(dark, accent, 0.4), width=1)

    def title(y, text, size, color):
        while size > 13 and draw.textlength(text, font=font(size)) > 580:
            size -= 1
        while draw.textlength(text, font=font(size)) > 580:
            text = text[:-2] + "…"
        draw.text((320, y), text, font=font(size), fill=color, anchor="mt")

    title(30, "YOU RECEIVED A SOULBOUND WEAPON", 17, theme.color)
    title(326, profile.weapon_name, 29, "#fff4fa")
    title(
        370,
        f"{profile.weapon_rarity.upper()}  /  {profile.weapon_type}  /  {profile.affinity_name}",
        16,
        rarity,
    )
    art = weapon_art(profile.weapon_family, theme.color, rarity)
    halo = Image.new("RGBA", art.size, theme.color)
    halo.putalpha(art.getchannel("A").point(lambda value: value // 3))
    halo = halo.filter(ImageFilter.GaussianBlur(9))
    palette_sample = base.copy()
    palette_sample.paste(halo, (190, 58), halo)
    palette_sample.paste(art, (190, 58), art)
    palette = palette_sample.quantize(colors=128)
    frames = []
    for i in range(48):
        phase = math.tau * i / 48
        frame = base.copy()
        d = ImageDraw.Draw(frame)
        d.ellipse((202, 70, 438, 306), outline=blend(dark, accent, 0.5), width=1)
        for n in range(8):
            angle = phase + n * math.tau / 8
            x, y = 320 + 119 * math.cos(angle), 188 + 119 * math.sin(angle)
            d.ellipse((x - 2, y - 2, x + 2, y + 2), fill=rarity)
        position = (190, 58 + round(math.sin(phase) * 4))
        frame.paste(halo, position, halo)
        frame.paste(art, position, art)
        frames.append(frame.quantize(palette=palette, dither=Image.Dither.NONE))
    output = BytesIO()
    frames[0].save(
        output,
        "GIF",
        save_all=True,
        append_images=frames[1:],
        duration=40,
        loop=0,
        disposal=1,
        optimize=False,
    )
    data = output.getvalue()
    if len(data) > MAX_WEAPON_BYTES:
        raise ValueError("Weapon animation exceeds upload budget")
    return data
