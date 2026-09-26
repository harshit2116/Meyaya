"""Distinct local image cards for Meyaya's profile studio."""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from bot.services.card_renderer import font, label
from bot.services.profile_aesthetic import (
    ProfileVisual,
    profile_affinity,
    profile_class,
    style_compatibility,
)


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def _mix(left: tuple[int, int, int], right: tuple[int, int, int], amount: float):
    return tuple(int(a + (b - a) * amount) for a, b in zip(left, right, strict=True))


def _background(size: tuple[int, int], primary: str, secondary: str) -> Image.Image:
    width, height = size
    dark = (12, 9, 19)
    left = _mix(_rgb(primary), dark, 0.68)
    right = _mix(_rgb(secondary), dark, 0.72)
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        color = _mix(left, right, y / max(1, height - 1))
        draw.line((0, y, width, y), fill=color)
    glow = Image.new("RGBA", size)
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((-180, -220, 520, 480), fill=(*_rgb(primary), 90))
    glow_draw.ellipse(
        (width - 440, height - 440, width + 170, height + 150), fill=(*_rgb(secondary), 95)
    )
    glow = glow.filter(ImageFilter.GaussianBlur(80))
    return Image.alpha_composite(image.convert("RGBA"), glow)


def _open(data: bytes | None) -> Image.Image | None:
    if not data:
        return None
    try:
        with Image.open(BytesIO(data)) as image:
            if image.width * image.height > 4_000_000:
                return None
            image.thumbnail((1024, 1024))
            return image.convert("RGBA")
    except (OSError, ValueError):
        return None


def _avatar(image: Image.Image, visual: ProfileVisual, box: tuple[int, int, int, int]) -> None:
    x, y, size, _ = box
    art = _open(visual.avatar)
    if art is None:
        art = Image.new("RGBA", (size, size), _rgb(visual.palette[1]) + (255,))
        fallback = ImageDraw.Draw(art)
        initial = visual.name[:1].upper() or "?"
        width = fallback.textlength(initial, font=font(size // 2))
        fallback.text(
            ((size - width) / 2, size * 0.19), initial, font=font(size // 2), fill="white"
        )
    art = ImageOps.fit(art, (size, size))
    mask = Image.new("L", (size, size))
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    image.paste(art, (x, y), mask)
    decoration = _open(visual.decoration)
    if decoration is not None:
        decoration = ImageOps.contain(decoration, (size + 38, size + 38))
        image.alpha_composite(decoration, (x - 19, y - 19))
    draw = ImageDraw.Draw(image)
    draw.ellipse((x - 3, y - 3, x + size + 3, y + size + 3), outline=visual.palette[2], width=4)


def _panel(draw: ImageDraw.ImageDraw, box, fill=(17, 14, 26, 188), outline=(255, 255, 255, 35)):
    draw.rounded_rectangle(box, radius=20, fill=fill, outline=outline, width=2)


def _score_bar(draw, x, y, width, name, value, color):
    draw.text((x, y), name.upper(), font=font(15), fill="#d8cfe0")
    draw.text((x + width - 37, y - 2), str(value), font=font(18), fill="white")
    draw.rounded_rectangle((x, y + 29, x + width, y + 40), radius=6, fill="#2a2533")
    draw.rounded_rectangle(
        (x, y + 29, x + max(10, width * value / 100), y + 40), radius=6, fill=color
    )


def _centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    center_x: int,
    y: int,
    max_width: int,
    size: int,
    fill: str,
    *,
    minimum_size: int = 14,
) -> None:
    """Draw one centered line, shrinking and truncating unusually long names."""

    clean = " ".join(text.split()) or "Unknown"
    chosen_size = size
    chosen_font = font(chosen_size)
    while chosen_size > minimum_size and draw.textlength(clean, font=chosen_font) > max_width:
        chosen_size -= 1
        chosen_font = font(chosen_size)
    if draw.textlength(clean, font=chosen_font) > max_width:
        while len(clean) > 1 and draw.textlength(f"{clean}…", font=chosen_font) > max_width:
            clean = clean[:-1]
        clean = f"{clean.rstrip()}…"
    draw.text((center_x, y), clean, font=chosen_font, fill=fill, anchor="ma")


def _centered_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    center_x: int,
    top: int,
    max_width: int,
    size: int,
    fill: str,
) -> None:
    """Wrap a short centered verdict without clipping it at the panel edge."""

    chosen_font = font(size)
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and draw.textlength(candidate, font=chosen_font) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    line_height = size + 7
    for index, line in enumerate(lines):
        draw.text(
            (center_x, top + index * line_height),
            line,
            font=chosen_font,
            fill=fill,
            anchor="ma",
        )


def _save(image: Image.Image) -> bytes:
    output = BytesIO()
    image.convert("RGB").save(output, "PNG", optimize=True)
    return output.getvalue()


PROFILECHECK_COMMENTS = (
    (
        92,
        "S+ - SERVER ICON",
        (
            "Annoyingly flawless. Meyaya searched for a weak point and came back empty-handed.",
            "This is not a profile anymore - it is a fully funded visual campaign.",
            "Main-character clearance granted. Everyone else may close their profile editor.",
            "Every detail agrees with the assignment. Suspiciously competent behavior.",
            "The colors, framing, and extras landed perfectly. No pity points were required.",
        ),
    ),
    (
        84,
        "S - ELITE",
        (
            "Polished enough to steal attention without begging for it.",
            "A seriously strong profile. One sharper detail would make it untouchable.",
            "This has identity, control, and just enough drama to be dangerous.",
            "The visual direction is clear and memorable. Meyaya has very little to roast.",
            "Excellent styling. It looks intentional instead of accidentally expensive.",
        ),
    ),
    (
        75,
        "A - DISTINCTIVE",
        (
            "Strong profile with a real point of view. It only needs a better finishing move.",
            "The aesthetic is working. Tighten the weakest element and this jumps a whole tier.",
            "Memorable, coordinated, and almost premium. Almost is doing some work there.",
            "Good taste is visible. A little more commitment would make it unmistakable.",
            "This profile knows what it wants to be and mostly delivers it.",
        ),
    ),
    (
        66,
        "B - STYLISH",
        (
            "Cute foundation, but one part of the profile clearly skipped rehearsal.",
            "The vibe exists and it is good. The execution still has room to become memorable.",
            "Above average and nicely coordinated, though the profile needs a stronger signature.",
            "A respectable look. Meyaya can see the vision, even if it is not fully rendered yet.",
            "Good ingredients, slightly cautious styling. Commit harder to the aesthetic.",
        ),
    ),
    (
        56,
        "C - DECENT",
        (
            "Not bad, not iconic. The profile is currently living in the safe middle.",
            "There is a vibe here, but it needs better color discipline and a focal point.",
            "Perfectly presentable. Unfortunately, presentable is not the same as memorable.",
            "The pieces work alone more than they work together. Give them one shared direction.",
            "This passes the profile check, but nobody is taking screenshots yet.",
        ),
    ),
    (
        45,
        "D - UNDERCOOKED",
        (
            "The profile arrived, but its aesthetic is still stuck in traffic.",
            "Meyaya sees individual choices, not a finished visual identity.",
            "Functional, but painfully cautious. Add contrast, coordination, or literally a plan.",
            "This needs a glow-up more than it needs another random decorative extra.",
            "The avatar is carrying the group project and would like some assistance.",
        ),
    ),
    (
        30,
        "E - ROUGH DRAFT",
        (
            "This is less of an aesthetic and more of a profile-shaped placeholder.",
            "The visual identity is missing. Meyaya recommends choosing one direction first.",
            "Nothing is fighting, but nothing is cooperating either. Start with a stronger avatar.",
            "The profile technically exists. The styling has not reported for duty.",
            "A blank canvas has potential, but Meyaya cannot grade potential like finished work.",
        ),
    ),
    (
        0,
        "F - PROFILE EMERGENCY",
        (
            "Meyaya has seen default settings with stronger artistic direction.",
            "This profile needs immediate aesthetic first aid and at least one deliberate choice.",
            "The score is not personal. The complete absence of styling, however, is very visible.",
            "There is nowhere to go but up, which is the nicest thing Meyaya can confirm.",
            "Profile review complete. Cause of failure: the aesthetic never entered the building.",
        ),
    ),
)


def profilecheck_feedback(visual: ProfileVisual) -> tuple[str, str, str]:
    """Return stable, score-specific criticism and one useful improvement target."""

    _, grade, comments = next(
        band for band in PROFILECHECK_COMMENTS if visual.overall_score >= band[0]
    )
    seed = int(visual.asset_fingerprint[-8:], 16) + visual.overall_score
    comment = comments[seed % len(comments)]
    scores = {
        "avatar": visual.avatar_score,
        "styling": visual.styling_score,
        "color harmony": visual.harmony_score,
        "originality": visual.originality_score,
    }
    weakest = min(scores, key=scores.get)
    tips = {
        "avatar": "Best upgrade: use a clearer avatar with stronger contrast and composition.",
        "styling": "Best upgrade: coordinate a banner, decoration, or server-specific avatar.",
        "color harmony": "Best upgrade: make the avatar and banner share a tighter color story.",
        "originality": "Best upgrade: add one signature detail that does not look copied from everyone else.",
    }
    return grade, comment, tips[weakest]


def profilecheck_card(visual: ProfileVisual) -> bytes:
    image = _background((1000, 720), visual.palette[3], visual.palette[0])
    draw = ImageDraw.Draw(image, "RGBA")
    _panel(draw, (28, 28, 972, 692))
    draw.text((58, 50), "MEYAYA PROFILE CHECK", font=font(18), fill=visual.palette[2])
    label(draw, (58, 86, 650, 56), visual.name, 40, "white")
    draw.text((770, 58), f"{visual.overall_score}", font=font(72), fill="white")
    draw.text((866, 103), "/ 100", font=font(21), fill=visual.palette[2])
    _avatar(image, visual, (62, 175, 270, 270))
    draw = ImageDraw.Draw(image, "RGBA")
    _panel(draw, (368, 174, 940, 455), fill=(10, 8, 18, 155))
    scores = (
        ("Avatar", visual.avatar_score),
        ("Styling", visual.styling_score),
        ("Color harmony", visual.harmony_score),
        ("Originality", visual.originality_score),
    )
    for index, (name, value) in enumerate(scores):
        _score_bar(draw, 402, 207 + index * 57, 495, name, value, visual.palette[index % 3])
    elements = [
        name
        for enabled, name in (
            (visual.has_banner, "Banner"),
            (visual.has_decoration, "Avatar decoration"),
            (visual.has_nameplate, "Nameplate"),
            (visual.has_server_tag, "Server tag"),
            (visual.has_server_avatar, "Server avatar"),
            (visual.animated_avatar, "Animated avatar"),
        )
        if enabled
    ]
    if visual.badge_count:
        elements.append(f"{visual.badge_count} public badge(s)")
    draw.text((62, 483), "PROFILE ELEMENTS", font=font(15), fill=visual.palette[2])
    label(
        draw, (62, 512, 875, 54), "  •  ".join(elements) or "Clean and minimal setup", 22, "white"
    )
    grade, verdict, tip = profilecheck_feedback(visual)
    _panel(draw, (58, 574, 942, 674), fill=(48, 35, 55, 255))
    draw.text((80, 589), grade, font=font(14), fill="#efb8d5")
    label(draw, (80, 612, 840, 27), verdict, 18, "white")
    label(draw, (80, 643, 840, 20), tip, 14, "#d7cadf")
    return _save(image)


AURA_ARCHETYPES = {
    "Moonlight": (
        "Silver Static",
        "Quiet Constellation",
        "Moonlit Echo",
        "Ivory Afterglow",
        "Starlight Witness",
    ),
    "Ember": (
        "Crimson Vanguard",
        "Scarlet Wildfire",
        "Ember Sovereign",
        "Ruby Defiance",
        "Flameheart Rebel",
    ),
    "Solar": (
        "Golden Daydream",
        "Sunlit Miracle",
        "Amber Crown",
        "Dawnbringer",
        "Honeyed Radiance",
    ),
    "Verdant": (
        "Verdant Whisper",
        "Emerald Sanctuary",
        "Wildflower Oath",
        "Forest Daydream",
        "Jade Wayfinder",
    ),
    "Tidal": (
        "Azure Oracle",
        "Sapphire Current",
        "Oceanborn Secret",
        "Cerulean Dreamer",
        "Tidebound Seer",
    ),
    "Astral": (
        "Violet Eclipse",
        "Astral Paradox",
        "Amethyst Mirage",
        "Cosmic Trouble",
        "Twilight Enigma",
    ),
    "Bloom": (
        "Rose Reverie",
        "Blushing Tempest",
        "Petal Enchantress",
        "Velvet Heartbeat",
        "Pink Supernova",
    ),
}

AURA_ESSENCES = (
    "calm until the plot needs a villain",
    "soft chaos with excellent timing",
    "quietly magnetic and fully aware of it",
    "dramatic in exactly the right amount",
    "gentle confidence with dangerous timing",
    "sweet energy hiding a competitive streak",
    "main-character calm before the storm",
    "warm presence with a sharp little edge",
    "dreamy on the surface, impossible underneath",
    "low-volume energy with high-impact entrances",
    "elegant confusion held together by confidence",
    "comforting until someone tests the patience",
    "playful mystery with suspiciously good taste",
    "bright energy carrying one secret villain arc",
    "quiet luxury with occasional gremlin behavior",
    "romantic lighting and tactical sarcasm",
    "unbothered energy with cinematic consequences",
    "soft-spoken charm with excellent comeback speed",
    "chaotic luck disguised as careful planning",
    "friendly warmth with final-boss potential",
)

AURA_SIGNATURES = (
    "observant • adaptable • vivid",
    "warm • expressive • fearless",
    "mysterious • loyal • creative",
    "playful • sharp • radiant",
    "composed • curious • magnetic",
    "dreamy • stubborn • sincere",
    "elegant • chaotic • unforgettable",
    "gentle • clever • unpredictable",
    "bold • devoted • theatrical",
    "witty • patient • luminous",
    "private • perceptive • powerful",
    "charming • restless • imaginative",
    "calm • stylish • dangerous",
    "soft • resilient • mischievous",
    "intuitive • loyal • dramatic",
    "bright • ambitious • strange",
    "graceful • daring • observant",
    "cozy • chaotic • confident",
    "honest • vivid • unshakable",
    "romantic • cunning • radiant",
)


def aura_details(visual: ProfileVisual) -> tuple[str, str, str, str]:
    """Build a stable aura with independently varied profile-born language."""

    affinity = profile_affinity(visual)
    digest = sha256(f"aura:{visual.asset_fingerprint}".encode("utf-8")).digest()
    titles = AURA_ARCHETYPES[affinity]
    title = titles[digest[0] % len(titles)]
    energy = AURA_ESSENCES[digest[7] % len(AURA_ESSENCES)]
    traits = AURA_SIGNATURES[digest[15] % len(AURA_SIGNATURES)]
    symbol = {
        "Moonlight": "✦",
        "Ember": "◆",
        "Solar": "☀",
        "Verdant": "❈",
        "Tidal": "◈",
        "Astral": "☾",
        "Bloom": "✿",
    }[affinity]
    return title, symbol, energy, traits


def aura_card(visual: ProfileVisual) -> bytes:
    image = _background((900, 650), visual.palette[0], visual.palette[4])
    draw = ImageDraw.Draw(image, "RGBA")
    title, _symbol, energy, traits = aura_details(visual)
    _panel(
        draw,
        (26, 26, 874, 624),
        fill=(11, 8, 19, 238),
        outline=(*_rgb(visual.palette[2]), 180),
    )
    seed = int(visual.asset_fingerprint, 16)
    for index in range(42):
        x = 45 + ((seed >> (index % 24)) + index * 83) % 810
        y = 42 + ((seed >> ((index + 7) % 28)) + index * 47) % 550
        radius = 1 + index % 2
        draw.ellipse(
            (x, y, x + radius, y + radius),
            fill=(*_rgb(visual.palette[2]), 115),
        )
    draw.ellipse((51, 137, 399, 485), fill=(*_rgb(visual.palette[0]), 35))
    draw.ellipse((67, 153, 383, 469), outline=visual.palette[2], width=3)
    draw.arc((46, 132, 404, 490), 205, 338, fill=visual.palette[1], width=7)
    draw.arc((46, 132, 404, 490), 18, 151, fill=visual.palette[4], width=7)
    _avatar(image, visual, (91, 177, 268, 268))
    draw = ImageDraw.Draw(image, "RGBA")
    draw.text((51, 46), "MEYAYA AURA ARCHIVE", font=font(16), fill="#f2cde1")
    label(draw, (51, 78, 550, 42), visual.name, 29, "white")
    draw.ellipse(
        (731, 50, 831, 150),
        fill=(*_rgb(visual.palette[0]), 80),
        outline=visual.palette[2],
        width=2,
    )
    monogram = "".join(part[:1] for part in title.split())
    draw.text((781, 98), monogram, font=font(30), fill="white", anchor="mm")
    draw.text((430, 172), "AURA ARCHETYPE", font=font(14), fill="#d6b1c9")
    label(draw, (430, 203, 390, 53), title, 38, "white")
    draw.text((430, 280), "ESSENCE", font=font(14), fill="#cfc4d7")
    label(draw, (430, 307, 375, 61), energy, 24, "#eac9da")
    draw.text((430, 390), "SIGNATURE", font=font(14), fill="#cfc4d7")
    label(draw, (430, 418, 380, 38), traits, 20, "white")
    _panel(draw, (430, 482, 816, 547), fill=(42, 31, 51, 255))
    label(
        draw,
        (451, 497, 340, 35),
        f"{profile_affinity(visual)} affinity  •  {profile_class(visual)}",
        18,
        "white",
    )
    for index, color in enumerate(visual.palette):
        x = 73 + index * 68
        draw.rounded_rectangle((x, 531, x + 51, 578), radius=12, fill=color)
    draw.text((73, 591), "PROFILE-BORN COLOR SIGNATURE", font=font(12), fill="#cfc4d7")
    return _save(image)


def palette_card(visual: ProfileVisual) -> bytes:
    image = _background((900, 500), "#17131f", visual.palette[3])
    draw = ImageDraw.Draw(image, "RGBA")
    draw.text((42, 36), "PROFILE PALETTE", font=font(17), fill=visual.palette[2])
    label(draw, (42, 72, 790, 48), visual.name, 34, "white")
    _avatar(image, visual, (56, 164, 220, 220))
    draw = ImageDraw.Draw(image, "RGBA")
    for index, color in enumerate(visual.palette):
        x = 322 + index * 105
        draw.rounded_rectangle((x, 168, x + 82, 340), radius=18, fill=color)
        width = draw.textlength(color.upper(), font=font(13))
        draw.text((x + (82 - width) / 2, 357), color.upper(), font=font(13), fill="white")
    label(
        draw,
        (322, 414, 510, 34),
        "A palette sampled from the visible avatar and banner.",
        18,
        "#ded4e5",
    )
    return _save(image)


DUOSTYLE_COMMENTS = (
    (
        88,
        (
            "Elite visual chemistry",
            "Same universe, premium casting",
            "Aesthetic power couple detected",
            "Two profiles, one flawless moodboard",
            "Ridiculously polished together",
            "The palettes understood each other",
        ),
    ),
    (
        76,
        (
            "Strong shared aesthetic",
            "Different flavors, excellent pairing",
            "Visually coordinated without trying",
            "A very convincing profile duo",
            "The color chemistry is doing numbers",
            "Almost an unfair amount of style",
        ),
    ),
    (
        63,
        (
            "A convincing style duo",
            "The profiles belong in one scene",
            "Good chemistry with separate identities",
            "A stylish pairing with real potential",
            "The contrast works more than it argues",
            "Meyaya approves the shared visual energy",
        ),
    ),
    (
        50,
        (
            "Some chemistry, some confusion",
            "Cute together, but not fully coordinated",
            "The profiles agree on alternate Tuesdays",
            "A workable duo with mixed signals",
            "Half harmony, half aesthetic debate",
            "The vibe connects, then loses signal",
        ),
    ),
    (
        35,
        (
            "Different visual universes",
            "The palettes met and chose awkward silence",
            "More contrast than actual chemistry",
            "Two good ideas having separate conversations",
            "The duo needs a stronger common thread",
            "Meyaya cannot locate the shared moodboard",
        ),
    ),
    (
        0,
        (
            "The palettes filed for separation",
            "A visual alliance was not formed today",
            "These profiles would unfollow on sight",
            "The aesthetic chemistry left the server",
            "Two planets with no connecting portal",
            "Meyaya recommends separate photoshoots",
        ),
    ),
)


def duostyle_feedback(
    left: ProfileVisual,
    right: ProfileVisual,
    compatibility: int,
) -> str:
    """Choose stable score-aware text while treating either user order equally."""

    comments = next(
        choices for threshold, choices in DUOSTYLE_COMMENTS if compatibility >= threshold
    )
    pair_seed = int(left.asset_fingerprint, 16) ^ int(right.asset_fingerprint, 16) ^ compatibility
    return comments[pair_seed % len(comments)]


def duostyle_card(left: ProfileVisual, right: ProfileVisual) -> bytes:
    image = _background((1100, 650), left.palette[0], right.palette[0])
    draw = ImageDraw.Draw(image, "RGBA")
    _panel(draw, (26, 26, 1074, 624), fill=(8, 7, 15, 205))
    draw.text((48, 44), "MEYAYA DUO STYLE", font=font(17), fill="#f5d5e7")
    draw.line((48, 79, 1052, 79), fill=(255, 255, 255, 35), width=1)
    compatibility = style_compatibility(left, right)
    _avatar(image, left, (96, 125, 260, 260))
    _avatar(image, right, (744, 125, 260, 260))
    draw = ImageDraw.Draw(image, "RGBA")

    # A fixed center panel prevents the score and verdict from floating between
    # differently-sized avatars or display names.
    _panel(
        draw,
        (421, 124, 679, 387),
        fill=(22, 17, 31, 238),
        outline=(*_rgb(left.palette[2]), 105),
    )
    draw.text((550, 154), "STYLE SYNC", font=font(14), fill="#d8cbdc", anchor="ma")
    draw.text(
        (550, 205),
        f"{compatibility}%",
        font=font(68),
        fill="white",
        anchor="ma",
    )
    verdict = duostyle_feedback(left, right, compatibility)
    _centered_wrapped_text(draw, verdict, 550, 304, 218, 17, "#f5d5e7")

    for visual, center_x in ((left, 226), (right, 874)):
        _panel(draw, (center_x - 176, 416, center_x + 176, 480), fill=(23, 18, 31, 230))
        _centered_text(draw, visual.name, center_x, 434, 310, 27, "white", minimum_size=17)
        draw.text(
            (center_x, 493),
            "PROFILE PALETTE",
            font=font(12),
            fill="#cfc3d5",
            anchor="ma",
        )
        x = center_x - 126
        for index, color in enumerate(visual.palette[:4]):
            draw.rounded_rectangle(
                (x + index * 66, 519, x + 54 + index * 66, 563),
                radius=11,
                fill=color,
                outline=(255, 255, 255, 28),
            )
    draw.line((421, 277, 679, 277), fill=(255, 255, 255, 28), width=1)
    _centered_text(
        draw,
        "Visual compatibility, not a relationship prediction.",
        550,
        584,
        700,
        15,
        "#d6cbdc",
        minimum_size=13,
    )
    return _save(image)


def callingcard_card(
    visual: ProfileVisual,
    *,
    nickname: str | None,
    relationship: str,
    titles: tuple[str, ...],
) -> bytes:
    image = _background((900, 700), visual.palette[3], visual.palette[0])
    draw = ImageDraw.Draw(image, "RGBA")
    _panel(draw, (40, 32, 860, 668), fill=(10, 8, 18, 175), outline=(*_rgb(visual.palette[2]), 130))
    draw.text((68, 56), "MEYAYA CALLING CARD", font=font(17), fill=visual.palette[2])
    _avatar(image, visual, (90, 150, 300, 300))
    draw = ImageDraw.Draw(image, "RGBA")
    label(draw, (430, 145, 370, 60), visual.name, 39, "white")
    label(
        draw,
        (430, 218, 370, 44),
        f'"{nickname}"' if nickname else "Nickname still loading...",
        25,
        visual.palette[2],
    )
    draw.text((430, 290), "MEYAYA'S BOND", font=font(14), fill="#cfc3d7")
    label(draw, (430, 318, 370, 54), relationship.title(), 24, "white")
    draw.text((430, 401), "EARNED TITLES", font=font(14), fill="#cfc3d7")
    label(draw, (430, 429, 370, 94), "\n".join(titles), 21, "white")
    draw.text((92, 505), "SIGNATURE COLORS", font=font(14), fill="#cfc3d7")
    for index, color in enumerate(visual.palette):
        draw.rounded_rectangle(
            (92 + index * 128, 544, 200 + index * 128, 604), radius=14, fill=color
        )
    label(
        draw,
        (92, 623, 690, 25),
        "A living card shaped by their Discord style and bond with Meyaya.",
        17,
        "#d9cfdf",
    )
    return _save(image)
