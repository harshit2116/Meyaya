"""Local, supersampled weapon illustrations and a gentle acquisition animation."""

from io import BytesIO
from hashlib import sha256
import math

from PIL import Image, ImageDraw, ImageFilter

from bot.data.fantasy import RARITIES, RARITY_COLORS, WEAPONS
from bot.services.card_renderer import font
from bot.services.fantasy_render import blend, rgb, theme_for

WEAPON_CARD_SIZE = (640, 420)
MAX_WEAPON_BYTES = 4 * 1024 * 1024


def _simple_weapon_art(family, accent, rarity):
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


def weapon_design(profile):
    """Catalogue suffix selects geometry; full saved ID selects fine engraving."""
    names = WEAPONS.get(profile.weapon_family, ("", ()))[1]
    variant = next(
        (
            i
            for i, name in enumerate(names)
            if profile.weapon_name.casefold().endswith(name.casefold())
        ),
        None,
    )
    seed = int.from_bytes(sha256(str(profile.weapon_id).encode()).digest()[:8], "big")
    return (variant if variant is not None else seed % 3), seed


def weapon_art(family, accent, rarity, design=0, seed=0):
    """Thirty authored silhouettes, faceted metal, rune inlays and variant hilts."""
    if family not in WEAPONS:
        return _simple_weapon_art(family, accent, rarity)
    v = design % 3
    im = Image.new("RGBA", (960, 960))
    d = ImageDraw.Draw(im)
    metal = ("#dce7fa", "#78879f", "#f4e7d2")[v]
    shadow = ("#50657f", "#232b42", "#957c69")[v]
    trim = ("#d9af63", "#b9d0e8", "#ecbe75")[v]

    def poly(points, fill=metal, edge=trim):
        d.polygon([(int(x * 3), int(y * 3)) for x, y in points], fill=fill, outline=edge, width=4)

    def line(points, fill=accent, width=3):
        d.line(
            [(int(x * 3), int(y * 3)) for x, y in points], fill=fill, width=width * 3, joint="curve"
        )

    def orb(x, y, r, color=accent):
        d.ellipse(
            ((x - r) * 3, (y - r) * 3, (x + r) * 3, (y + r) * 3), fill=color, outline=trim, width=4
        )
        d.ellipse(((x - r * 0.5) * 3, (y - r * 0.6) * 3, x * 3, y * 3), fill="#fff4e1")

    def haft(x=160, top=140, end=291):
        poly([(x - 7, top), (x + 7, top), (x + 6, end), (x - 6, end)], "#25263c")
        for y in range(max(top + 10, 220), end - 3, 8):
            line([(x - 6, y), (x + 6, y - 4)], trim, 1)
        orb(x, end, 8, rarity)

    def blade(x, top, end, width, variant=v):
        if variant == 0:
            pts = [
                (x, top),
                (x + width, top + 38),
                (x + width * 0.7, end),
                (x - width * 0.7, end),
                (x - width, top + 38),
            ]
        elif variant == 1:
            pts = [
                (x - width * 0.65, top),
                (x - 3, top + 22),
                (x + width * 0.8, top - 3),
                (x + width, top + 58),
                (x + width * 0.45, top + 78),
                (x + width * 1.25, top + 96),
                (x + width * 0.45, top + 118),
                (x + width * 1.25, top + 139),
                (x + width * 0.5, top + 161),
                (x + width * 0.7, end),
                (x - width * 0.8, end),
            ]
        else:
            pts = [
                (x + width * 0.5, top),
                (x + width * 1.3, top + 44),
                (x + width * 0.4, top + 75),
                (x + width, end),
                (x - width, end),
                (x - width * 0.6, top + 70),
                (x - width * 1.2, top + 40),
            ]
        poly(pts)
        poly(
            [(x, top + 18), (x, end - 3), (x - width * 0.55, end - 3), (x - width * 0.6, top + 40)],
            shadow,
            shadow,
        )
        line([(x + 4, top + 32), (x + 5, end - 8)], "#fff0d0", 1)
        for y in range(top + 58, end - 10, 23):
            line([(x - 4, y - 4), (x + 3, y), (x - 4, y + 4)], accent, 2)
        poly(
            [
                (x - 38, end),
                (x - 20, end - 9),
                (x, end - 3),
                (x + 20, end - 9),
                (x + 38, end),
                (x + 25, end + 12),
                (x, end + 7),
                (x - 25, end + 12),
            ],
            trim,
        )
        haft(x, end + 7, min(291, end + 62))
        orb(x, end + 3, 9, rarity)
        if family == "greatsword":
            # Large crown-like guard and suspended ring distinguish colossal blades.
            for side in (-1, 1):
                poly(
                    [
                        (x + side * 12, end + 5),
                        (x + side * 45, end - 15),
                        (x + side * 56, end - 38),
                        (x + side * 53, end + 11),
                        (x + side * 26, end + 23),
                    ],
                    shadow,
                )
            d.ellipse(
                ((x - 14) * 3, (end + 21) * 3, (x + 14) * 3, (end + 49) * 3), outline=trim, width=5
            )

    if family in {"sword", "greatsword", "daggers"}:
        if family == "daggers":
            blade(103, 47, 206, 18)
            blade(217, 72, 228, 18, variant=(v + 1) % 3)
        else:
            blade(160, 19, 228, 34 if family == "greatsword" else 23)
            if family == "greatsword":
                for side in (-1, 1):
                    poly(
                        [(160 + side * 25, 160), (160 + side * 48, 178), (160 + side * 24, 201)],
                        shadow,
                    )
    elif family == "katana":
        curves = [
            [(119, 29), (146, 83), (163, 149), (179, 226)],
            [(98, 27), (131, 74), (163, 139), (185, 218)],
            [(76, 35), (116, 69), (153, 118), (177, 174), (188, 224)],
        ][v]
        line(curves, shadow, 20)
        line([(x + 4, y) for x, y in curves], metal, 13)
        line([(x + 10, y) for x, y in curves], "#fff1df", 2)
        line([(x - 1, y) for x, y in curves], accent, 2)
        x, y = curves[-1]
        if v == 2:
            poly(
                [(x - 28, y), (x - 16, y - 18), (x + 23, y - 10), (x + 29, y + 8), (x, y + 16)],
                trim,
            )
        else:
            orb(x, y, 19, shadow)
        haft(x, y, 292)
    elif family == "spear":
        haft(top=98)
        if v == 0:
            poly([(160, 17), (174, 107), (160, 136), (146, 107)])
            for side in (-1, 1):
                line([(160 + side * 8, 119), (160 + side * 38, 96), (160 + side * 40, 44)], trim, 7)
                poly([(160 + side * 40, 28), (160 + side * 49, 59), (160 + side * 31, 59)])
        elif v == 1:
            poly([(160, 12), (186, 78), (172, 126), (160, 150), (147, 124), (134, 78)])
        else:
            poly(
                [
                    (160, 19),
                    (210, 61),
                    (216, 92),
                    (187, 130),
                    (167, 141),
                    (192, 91),
                    (154, 72),
                    (135, 121),
                ]
            )
        line([(160, 45), (160, 125)], accent, 3)
        orb(160, 137, 10, rarity)
    elif family == "axe":
        haft(top=60)
        if v == 0:
            for side in (-1, 1):
                poly(
                    [
                        (160 + side * 9, 70),
                        (160 + side * 51, 48),
                        (160 + side * 83, 26),
                        (160 + side * 76, 113),
                        (160 + side * 43, 143),
                        (160 + side * 10, 107),
                    ]
                )
        elif v == 1:
            poly(
                [
                    (148, 62),
                    (187, 62),
                    (232, 37),
                    (242, 91),
                    (220, 123),
                    (187, 149),
                    (199, 110),
                    (145, 108),
                ]
            )
            poly([(154, 70), (111, 34), (127, 90)], shadow)
        else:
            poly(
                [
                    (149, 44),
                    (202, 30),
                    (236, 46),
                    (221, 63),
                    (245, 82),
                    (217, 87),
                    (238, 108),
                    (206, 139),
                    (149, 112),
                ]
            )
        orb(160, 91, 16, rarity)
        line([(177, 79), (201, 92), (178, 105)], accent, 3)
    elif family == "mace":
        haft(top=124)
        if v == 0:
            pts = []
            for i in range(20):
                ang = math.tau * i / 20
                r = 67 if i % 2 == 0 else 41
                pts.append((160 + math.cos(ang) * r, 88 + math.sin(ang) * r))
            poly(pts, shadow)
            orb(160, 88, 34, metal)
        elif v == 1:
            poly(
                [
                    (112, 40),
                    (207, 40),
                    (223, 61),
                    (219, 123),
                    (199, 141),
                    (120, 132),
                    (99, 105),
                    (100, 61),
                ],
                shadow,
            )
            poly([(114, 49), (199, 49), (207, 115), (119, 119)])
            for x in (126, 150, 174, 198):
                line([(x, 59), (x, 114)], trim, 3)
        else:
            poly(
                [
                    (109, 111),
                    (122, 60),
                    (118, 27),
                    (144, 51),
                    (160, 17),
                    (177, 51),
                    (200, 27),
                    (198, 63),
                    (215, 114),
                    (180, 143),
                    (140, 143),
                ],
                shadow,
            )
            orb(160, 91, 25, rarity)
        orb(160, 137, 11, accent)
    elif family == "staff":
        haft(top=115)
        if v == 0:
            d.arc((94 * 3, 16 * 3, 226 * 3, 151 * 3), 15, 340, fill=trim, width=8 * 3)
            poly([(160, 28), (185, 78), (160, 126), (135, 78)], accent)
        elif v == 1:
            poly([(114, 44), (160, 23), (205, 44), (197, 115), (160, 137), (122, 115)], shadow)
            poly([(130, 48), (188, 48), (182, 111), (138, 111)], accent)
            for x in (138, 160, 182):
                line([(x, 43), (x, 119)], trim, 3)
            line([(160, 24), (160, 10)], trim, 5)
        else:
            for x, y in ((113, 65), (160, 34), (207, 65)):
                line([(160, 130), (x, y + 20)], trim, 7)
                orb(x, y, 21, accent)
        orb(160, 150, 10, rarity)
    elif family == "bow":
        pts = [
            [(173, 28), (209, 62), (221, 114), (201, 160), (221, 206), (209, 260), (173, 293)],
            [(181, 25), (237, 53), (222, 101), (239, 151), (222, 205), (237, 261), (181, 295)],
            [
                (174, 22),
                (232, 64),
                (254, 100),
                (218, 132),
                (217, 192),
                (254, 226),
                (231, 257),
                (174, 297),
            ],
        ][v]
        line(pts, shadow, 14)
        line([(x - 3, y) for x, y in pts], trim, 5)
        line([(pts[0][0], pts[0][1]), (170, 160), (pts[-1][0], pts[-1][1])], "#dfeaff", 1)
        if v == 1:
            orb(221, 55, 19, metal)
            orb(221, 266, 19, metal)
        if v == 2:
            for y in (76, 104, 216, 244):
                poly([(226, y), (270, y - 20), (250, y + 15)], metal)
        line([(62, 160), (260, 160)], trim, 4)
        poly([(291, 160), (258, 145), (258, 175)])
        poly([(54, 160), (78, 141), (104, 141), (86, 160), (104, 179), (78, 179)], accent)
        orb(205, 160, 12, rarity)
    else:  # Spellbook: sealed codex, open tome, suspended rune tablets.
        if v == 0:
            poly([(79, 49), (232, 39), (249, 256), (91, 274)], shadow)
            poly([(88, 56), (224, 50), (236, 247), (98, 259)], "#383448")
            for x, y in ((91, 63), (221, 57), (107, 248), (227, 239)):
                poly([(x, y - 9), (x + 10, y), (x, y + 9), (x - 10, y)], trim)
            poly([(127, 152), (161, 111), (202, 143), (164, 180)], accent)
            orb(164, 146, 16, rarity)
        elif v == 1:
            poly(
                [
                    (43, 79),
                    (137, 54),
                    (160, 74),
                    (183, 54),
                    (277, 79),
                    (269, 260),
                    (182, 240),
                    (160, 256),
                    (138, 240),
                    (51, 260),
                ],
                shadow,
            )
            poly([(53, 86), (145, 70), (153, 85), (153, 238), (62, 250)], "#ecdcc7")
            poly([(166, 85), (180, 70), (267, 86), (256, 250), (166, 238)], "#c5b89f")
            line([(160, 76), (160, 246)], trim, 3)
            orb(211, 157, 29, accent)
        else:
            for x, y, w in ((59, 92, 62), (131, 51, 71), (212, 102, 53)):
                poly([(x, y), (x + w, y - 10), (x + w + 5, y + 151), (x + 3, y + 162)], shadow)
                line(
                    [
                        (x + 10, y + 12),
                        (x + w - 9, y + 7),
                        (x + w - 8, y + 137),
                        (x + 13, y + 143),
                        (x + 10, y + 12),
                    ],
                    trim,
                    2,
                )
                for yy in range(y + 39, y + 118, 22):
                    line([(x + 21, yy), (x + w - 17, yy - 4)], accent, 2)
    # Saved-ID-specific engraving: four different rune/crest arrangements.
    for i in range(3 + seed % 4):
        angle = math.tau * i / (3 + seed % 4)
        x, y = 160 + math.cos(angle) * 12, 160 + math.sin(angle) * 12
        d.ellipse((x * 3 - 3, y * 3 - 3, x * 3 + 3, y * 3 + 3), fill=rarity)
    return im.resize((260, 260), Image.Resampling.LANCZOS)


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
    design, seed = weapon_design(profile)
    art = weapon_art(profile.weapon_family, theme.color, rarity, design, seed)
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
