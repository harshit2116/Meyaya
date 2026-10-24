"""Distinct local image cards for Meyaya's profile studio."""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from collections import OrderedDict
from bisect import bisect_right
from math import lcm
from functools import lru_cache
from bot.services.profile_badges import badge_icon
import logging
import math
from time import monotonic

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from bot.services.card_renderer import font, label
from bot.services.profile_scoring import category_available, build_improvement_summary, get_rule_based_recommendation, select_improvement_priority
from bot.services.profile_aesthetic import (
    ProfileVisual,
    profilecheck_points,
    profile_affinity,
    profile_class,
    style_compatibility,
)


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def _mix(left: tuple[int, int, int], right: tuple[int, int, int], amount: float):
    return tuple(int(a + (b - a) * amount) for a, b in zip(left, right, strict=True))


def _readable_accent(color: str, background: str, minimum: float = 4.5) -> str:
    """Lift dark avatar colors until they remain readable on the card surface."""
    def luminance(rgb):
        channels = [value / 255 for value in rgb]
        linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
                  for value in channels]
        return sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

    original = _rgb(color)
    surface = luminance(_rgb(background))
    for step in range(101):
        candidate = _mix(original, (255, 255, 255), step / 100)
        light = luminance(candidate)
        if (max(light, surface) + 0.05) / (min(light, surface) + 0.05) >= minimum:
            return '#%02x%02x%02x' % candidate
    return '#ffffff'


_BACKGROUNDS = OrderedDict()
_BACKGROUND_BUDGET = 4 * 1024 * 1024


def _background(size: tuple[int, int], primary: str, secondary: str) -> Image.Image:
    # Only called on the single Pillow worker. Copy so callers cannot alter
    # another member's card; cap decoded pixels, not compressed file size.
    key = (size, primary, secondary)
    cached = _BACKGROUNDS.get(key)
    if cached is not None:
        _BACKGROUNDS.move_to_end(key)
        return cached.copy()
    image = _build_background(size, primary, secondary)
    cost = image.width * image.height * 4
    if cost <= _BACKGROUND_BUDGET:
        while _BACKGROUNDS and sum(v.width * v.height * 4 for v in _BACKGROUNDS.values()) + cost > _BACKGROUND_BUDGET:
            _, old = _BACKGROUNDS.popitem(last=False)
            old.close()
        _BACKGROUNDS[key] = image.copy()
    return image


def _build_background(size: tuple[int, int], primary: str, secondary: str) -> Image.Image:
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
    except (OSError, ValueError, Image.DecompressionBombError):
        return None


def _avatar(image: Image.Image, visual: ProfileVisual, box: tuple[int, int, int, int]) -> None:
    _avatar_art(image, visual, box, _open(visual.avatar), _open(visual.decoration))


def _avatar_art(image, visual, box, art, decoration) -> None:
    x, y, size, _ = box
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
    if decoration is not None:
        decoration = ImageOps.contain(decoration, (size + 38, size + 38))
        image.alpha_composite(decoration, (x - 19, y - 19))
    draw = ImageDraw.Draw(image)
    draw.ellipse((x - 3, y - 3, x + size + 3, y + size + 3), outline=visual.palette[2], width=4)


def _panel(draw: ImageDraw.ImageDraw, box, fill=(17, 14, 26, 188), outline=(255, 255, 255, 35)):
    draw.rounded_rectangle(box, radius=20, fill=fill, outline=outline, width=2)


def _score_bar(draw, x, y, width, name, value, color, *, points_text=None):
    draw.text((x, y), name.upper(), font=font(15), fill="#d8cfe0")
    if points_text is not None:
        draw.text((x + width, y - 2), points_text, anchor="ra", font=font(18), fill="white")
    else:
        draw.text((x + width - 37, y - 2), str(value), font=font(18), fill="white")
    draw.rounded_rectangle((x, y + 29, x + width, y + 40), radius=6, fill="#2a2533")
    if value > 0:
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
    image.convert("RGB").save(output, "PNG", compress_level=3)
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

    _, grade, _ = next(
        band for band in PROFILECHECK_COMMENTS if visual.overall_score >= band[0]
    )
    return grade, build_improvement_summary(visual), get_rule_based_recommendation(visual)


def profilecheck_card(visual: ProfileVisual) -> bytes:
    return _save(_profilecheck_image(visual))


PROFILECHECK_SIZE = (1500, 1000)
PROFILECHECK_BANNER = (48, 147, 1404, 300)
PROFILECHECK_AVATAR = (64, 400, 280, 280)
PROFILECHECK_ANIMATION_WIDTH = 1000


def _profile_spark(draw, x, y, size, color):
    points = []
    for i in range(8):
        angle = i * math.pi / 4
        radius = size if i % 2 == 0 else size * .25
        points.append((x+math.sin(angle)*radius, y+math.cos(angle)*radius))
    draw.polygon(points, fill=color)


def _profile_flower(draw, x, y, size, color):
    for i in range(5):
        angle = i * math.tau / 5
        tip = (x+math.sin(angle)*size, y+math.cos(angle)*size)
        left = (x+math.sin(angle-.38)*size*.38, y+math.cos(angle-.38)*size*.38)
        right = (x+math.sin(angle+.38)*size*.38, y+math.cos(angle+.38)*size*.38)
        draw.polygon([(x,y),left,tip,right],fill=color)
    draw.ellipse((x-3,y-3,x+3,y+3),fill="#e9aec7")


@lru_cache(maxsize=1)
def _profilecheck_frame():
    # Brand decoration is shared, copied before any member's assets are painted.
    image = Image.new("RGBA", PROFILECHECK_SIZE, "#251c28")
    draw = ImageDraw.Draw(image)
    for x,y,r in ((0,210,70),(1485,550,40),(38,760,60),(1420,970,65)):
        _profile_flower(draw,x,y,r,"#352332")
    draw.rounded_rectangle((26,26,1474,974),radius=22,fill="#120f19",outline="#c39bb1",width=2)
    _profile_flower(draw,79,83,26,"#ed95b6")
    # Small ornamental flourishes stay outside the banner and reading areas.
    draw.line((580,73,704,73),fill="#8f647f",width=1)
    _profile_spark(draw,575,73,4,"#eea4c2")
    _profile_spark(draw,708,73,3,"#bd82a3")
    for x,y,r in ((1452,52,7),(1420,936,26),(1456,887,20)):
        _profile_flower(draw,x,y,r,"#46303f")
    return image


@lru_cache(maxsize=1)
def _profilecheck_banner_mask():
    _, _, width, height = PROFILECHECK_BANNER
    mask = Image.new("L", (width, height))
    ImageDraw.Draw(mask).rounded_rectangle((0,0,width-1,height-1),radius=22,fill=255)
    return mask


def _profilecheck_banner(image, banner):
    x,y,width,height = PROFILECHECK_BANNER
    image.paste(ImageOps.fit(banner,(width,height)),(x,y),_profilecheck_banner_mask())


def _profile_score_icon(draw, kind, x, y, color):
    if kind == 0:
        draw.ellipse((x-13,y-8,x+13,y+8),outline=color,width=3)
        draw.ellipse((x-4,y-4,x+4,y+4),fill=color)
    elif kind == 1:
        draw.rounded_rectangle((x-13,y-10,x+4,y+3),radius=5,outline=color,width=3)
        draw.rounded_rectangle((x-3,y-2,x+14,y+11),radius=5,outline=color,width=3)
    elif kind == 2:
        draw.ellipse((x-12,y-11,x+12,y+11),fill=color)
        for dx,dy in ((-5,-4),(2,-6),(6,0),(-6,3)):
            draw.ellipse((x+dx-2,y+dy-2,x+dx+2,y+dy+2),fill="#251b2a")
    else:
        _profile_spark(draw,x,y,13,color)


def _profilecheck_score_overlay(visual):
    overlay = Image.new("RGBA",PROFILECHECK_SIZE)
    draw = ImageDraw.Draw(overlay)
    draw.line((716,470,716,706),fill="#6d4d65",width=1)
    draw.text((798,473),"STYLE BREAKDOWN",font=font(19),fill="#cdaac5")
    draw.text((1435,473),"SCORE",font=font(16),anchor="ra",fill="#cdaac5")
    colors = ("#ed84a5","#ca86e8","#b77caa","#f1b6cf")
    for index,(field,name,_,_) in enumerate(profilecheck_points(visual)):
        y = 519 + index * 52
        available = category_available(visual,field)
        value = max(0,min(100,getattr(visual,field)))
        _profile_score_icon(draw,index,770,y+14,colors[index])
        draw.text((803,y),name,font=font(22),fill="#f4e9f2")
        draw.rounded_rectangle((966,y+7,1320,y+25),radius=9,fill="#302737")
        if available and value:
            draw.rounded_rectangle((966,y+7,966+max(18,354*value/100),y+25),radius=9,fill=colors[index])
        draw.text((1435,y),f"{value} / 100" if available else "N/A",font=font(22),anchor="ra",fill="#efacc9")
        if index < 3:
            draw.line((798,y+40,1435,y+40),fill="#483347",width=1)
    return overlay


def _profilecheck_avatar(image, visual, art, decoration):
    x,y,size,_ = PROFILECHECK_AVATAR
    draw = ImageDraw.Draw(image)
    draw.ellipse((x-11,y-11,x+size+11,y+size+11),fill="#120f1b",outline="#e18cae",width=2)
    _avatar_art(image,visual,PROFILECHECK_AVATAR,art,decoration)
    # Ornamentation frames the avatar without covering the face or decoration.
    draw = ImageDraw.Draw(image)
    for dx,dy,r in ((-7,45,12),(size+5,34,11),(size+10,size-40,12),(-5,size-25,10)):
        _profile_spark(draw,x+dx,y+dy,r,"#efa3c2")


def _profilecheck_identity(draw, visual):
    # Fit the nickname and server tag on the same line, inside the existing
    # identity column. Long names yield space to the tag without entering scores.
    tag = visual.server_tag
    tag_width = min(108, round(draw.textlength(tag, font=font(18)))+24) if tag else 0
    available = 318-tag_width-(14 if tag else 0)
    size = 43
    name = visual.name
    while size > 26 and draw.textlength(name, font=font(size)) > available:
        size -= 1
    while len(name) > 1 and draw.textlength(name, font=font(size)) > available:
        name = name[:-2] + "…"
    draw.text((378, 490), name, font=font(size), fill="#fff0f8")
    if tag:
        x = round(378+draw.textlength(name, font=font(size))+14)
        draw.rounded_rectangle((x, 495, x+tag_width, 528), radius=10,
                               fill="#382b43", outline="#9d6f9e", width=1)
        label(draw, (x+12, 502, tag_width-24, 22), tag, 18, "#e2b4e9", minimum=14)
    if visual.username:
        label(draw, (378, 553, 318, 30), "@"+visual.username.lstrip("@"),
              21, "#a994aa", minimum=16)


def _profilecheck_image(visual: ProfileVisual, *, include_avatar: bool = True,
                       include_scores: bool = True) -> Image.Image:
    image = _profilecheck_frame().copy()
    draw = ImageDraw.Draw(image)
    draw.text((130,51),"MEYAYA / PROFILE CHECK",font=font(32),fill="#f9e5f0")
    draw.text((132,99),"A QUICK LOOK AT YOUR DISCORD PROFILE STYLE",font=font(17),fill="#c7a6c0")
    grade,verdict,tip = profilecheck_feedback(visual)
    draw.rounded_rectangle((1018,44,1452,136),radius=18,fill="#17121e",outline="#e8a1bf",width=2)
    draw.rounded_rectangle((1038,60,1227,98),radius=11,fill="#472e3e",outline="#d37e9e",width=1)
    label(draw,(1053,69,164,25),grade.replace(" - "," · "),17,"#ffe6f2",minimum=13)
    draw.text((1039,109),"STYLE SCORE",font=font(15),fill="#ed9fbd")
    draw.text((1347,45),str(visual.overall_score),font=font(75),anchor="ra",fill="#f6b0ca")
    draw.text((1433,95),"/ 100",font=font(25),anchor="ra",fill="#bc94ae")
    _profile_spark(draw,1433,59,10,"#e994b7")
    banner = _open(visual.banner)
    if banner is None:
        color = visual.accent_color if not visual.banner_available else None
        banner = Image.new("RGBA",PROFILECHECK_BANNER[2:],color or visual.palette[3])
    _profilecheck_banner(image,banner)
    if include_avatar:
        _profilecheck_avatar(image,visual,_open(visual.avatar),_open(visual.decoration))
    plate = _open(visual.nameplate)
    if plate is not None:
        image.alpha_composite(ImageOps.fit(plate,(324,66)),(365,482))
        image.alpha_composite(Image.new("RGBA",(324,66),(12,9,19,100)),(365,482))
    draw = ImageDraw.Draw(image)
    _profilecheck_identity(draw, visual)
    for index,name in enumerate(visual.badge_names[:11]):
        icon = badge_icon(name)
        if icon is not None:
            image.alpha_composite(icon,(378+(index%6)*48,620+(index//6)*46))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((48,730,1452,922),radius=20,fill="#221923",outline="#e3a0c0",width=2)
    _profile_spark(draw,91,763,14,"#f39fbe")
    draw.text((123,747),"YOUR BIGGEST OPPORTUNITY",font=font(25),fill="#f395b6")
    critique = getattr(visual, "critique", None)
    if critique is not None:
        labels = {"readability": "Readability", "cohesion": "Cohesion",
                  "color_harmony": "Color harmony", "detail_balance": "Detail balance"}
        priority = labels[critique.findings[0].metric] if critique.findings else "Visual check"
    else:
        _,priority,_ = select_improvement_priority(visual)
    pill_text = priority.upper()
    pill_width = round(draw.textlength(pill_text, font=font(18)))+32
    pill_left = 1430-pill_width
    draw.rounded_rectangle((pill_left,746,1430,790),radius=14,fill="#38263d",outline="#a8759e",width=1)
    label(draw,(pill_left+16,756,pill_width-32,28),pill_text,18,"#e8b6e7",minimum=14)
    draw.line((89,804,89,897),fill="#d08eac",width=2)
    label(draw,(123,800,1273,37),verdict,27,"#fff0f8",minimum=23)
    label(draw,(123,844,1273,62),tip.removeprefix("Best upgrade: "),24,"#d9bfd4",minimum=20)
    draw.text((64,941),"Visual estimate · Public profile elements only",font=font(18),fill="#a38a9f")
    if include_scores:
        image.alpha_composite(_profilecheck_score_overlay(visual))
    return image


PROFILE_ANIMATION_MS = 8_000
PROFILE_ANIMATION_FRAMES = 90
PROFILE_ANIMATION_DECODE_BYTES = 64 * 1024 * 1024
PROFILE_MEDIA_BYTES = 8 * 1024 * 1024


def _animation_frame_delay(source):
    # Browsers interpret GIF delays <=10 ms as 100 ms. Clamping them to
    # 20 ms instead makes a re-encoded GIF play five times faster in Discord.
    # https://issues.chromium.org/issues/41352431
    delay = float(source.info.get("duration", 100) or 100)
    if not math.isfinite(delay) or delay < 0:
        delay = 100
    if source.format == "GIF" and delay <= 10:
        return 100
    return max(20, delay)


def _animation_timeline(sources):
    """Loop assets by elapsed time, preserving exact frame boundaries when bounded."""
    duration = min(PROFILE_ANIMATION_MS, lcm(*(ends[-1] for _, ends in sources.values())))
    boundaries = {0, duration}
    for _, ends in sources.values():
        for offset in range(0, duration, ends[-1]):
            boundaries.update(offset + end for end in ends if offset + end < duration)
    times = sorted(boundaries)
    if len(times) - 1 > PROFILE_ANIMATION_FRAMES:
        # Sample dense animations without speeding up or slowing down playback.
        step = max(20, ((duration + PROFILE_ANIMATION_FRAMES * 10 - 1)
                        // (PROFILE_ANIMATION_FRAMES * 10)) * 10)
        times = [*range(0, duration, step), duration]
    # Different assets can introduce boundaries only 10 ms apart. Such GIF
    # frames are slowed to 100 ms by browsers; merge samples, keeping elapsed
    # playback time intact instead of handing those tiny delays to the client.
    playable = [0]
    for boundary in times[1:-1]:
        if boundary-playable[-1] >= 20:
            playable.append(boundary)
    if len(playable) > 1 and duration-playable[-1] < 20:
        playable.pop()
    return [*playable, duration]


def profilecheck_media(visual: ProfileVisual, *, max_bytes=PROFILE_MEDIA_BYTES) -> tuple[bytes, str]:
    """Render bounded full cycles; complex/oversized assets fall back to a static card."""
    sources = {}
    frames = []
    deadline = monotonic() + 12
    decoded_bytes = 0
    try:
        for key in ("avatar", "banner", "decoration"):
            data = getattr(visual, key)
            if not data:
                continue
            with Image.open(BytesIO(data)) as source:
                if not getattr(source, "is_animated", False):
                    continue
                if source.width * source.height > 4_000_000:
                    raise ValueError("animated asset exceeds pixel budget")
                decoded, ends = [], []
                elapsed_ms = 0.0
                sources[key] = (decoded, ends)
                # Store at delivery resolution, not full CDN resolution.
                size = {"avatar": (187, 187), "banner": (936, 200), "decoration": (213, 213)}[key]
                for index in range(300):
                    if monotonic() > deadline:
                        raise ValueError("animation exceeded render time budget")
                    try:
                        source.seek(index)
                    except EOFError:
                        break
                    frame = source.convert("RGBA")
                    frame.thumbnail(size)
                    decoded.append(frame)
                    decoded_bytes += frame.width * frame.height * 4
                    if decoded_bytes > PROFILE_ANIMATION_DECODE_BYTES:
                        raise ValueError("animation exceeded decoded memory budget")
                    elapsed_ms += _animation_frame_delay(source)
                    # GIF uses centiseconds. Round cumulative timestamps, not
                    # every frame: 33 ms frames must not all become 30 ms.
                    ends.append(min(PROFILE_ANIMATION_MS, round(elapsed_ms / 10) * 10))
                    if ends[-1] >= PROFILE_ANIMATION_MS:
                        break
        if not sources:
            return profilecheck_card(visual), "png"
        # Paint text, gradients and score bars once, not once per GIF frame.
        # A clean template also prevents transparent decorations leaving trails.
        template = _profilecheck_image(visual, include_avatar=False)
        static_art = {key: _open(getattr(visual, key)) for key in ("avatar", "decoration")
                      if key not in sources}
        times = _animation_timeline(sources)
        durations = [end - start for start, end in zip(times, times[1:])]
        for elapsed in times[:-1]:
            if monotonic() > deadline:
                raise ValueError("animation exceeded render time budget")
            changes = {
                key: decoded[bisect_right(ends, elapsed % ends[-1])]
                for key, (decoded, ends) in sources.items()
            }
            rendered = template.copy()
            if "banner" in changes:
                _profilecheck_banner(rendered, changes["banner"])
            _profilecheck_avatar(rendered, visual,
                        changes.get("avatar", static_art.get("avatar")),
                        changes.get("decoration", static_art.get("decoration")))
            frames.append(rendered.resize((PROFILECHECK_ANIMATION_WIDTH, round(rendered.height * PROFILECHECK_ANIMATION_WIDTH / rendered.width))).convert("P", palette=Image.Palette.ADAPTIVE, colors=128))
            rendered.close()
        output = BytesIO()
        frames[0].save(output, "GIF", save_all=True, append_images=frames[1:], duration=durations, loop=0, disposal=2)
        if output.tell() <= min(max_bytes, PROFILE_MEDIA_BYTES):
            return output.getvalue(), "gif"
        logging.getLogger(__name__).info("profile_animation_static_fallback reason=upload_size bytes=%s", output.tell())
    except (OSError, ValueError, EOFError, Image.DecompressionBombError) as error:
        logging.getLogger(__name__).warning("profile_animation_static_fallback reason=%s", type(error).__name__)
    finally:
        for decoded, _ in sources.values():
            for frame in decoded:
                frame.close()
        for frame in frames:
            frame.close()
    return profilecheck_card(visual), "png"


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
    from bot.services.aura_archive import render_archive

    title, _, energy, traits = aura_details(visual)
    return _save(render_archive(visual, title=title, energy=energy, traits=traits,
        affinity=profile_affinity(visual), class_name=profile_class(visual)))


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
    from bot.services.duostyle_archive import render_duo

    compatibility = style_compatibility(left, right)
    return _save(render_duo(left, right, score=compatibility,
        verdict=duostyle_feedback(left, right, compatibility), reason=duostyle_reason(left, right)))


def duostyle_reason(left: ProfileVisual, right: ProfileVisual) -> str:
    """Describe observable palette differences without another model call."""
    a, b = [_rgb(c) for c in left.palette[:4]], [_rgb(c) for c in right.palette[:4]]
    distance = sum(min(sum((x-y)**2 for x,y in zip(c,d))**0.5 for d in b) for c in a) / len(a)
    reverse = sum(min(sum((x-y)**2 for x,y in zip(c,d))**0.5 for d in a) for c in b) / len(b)
    brightness = lambda colors: sum(.2126*r + .7152*g + .0722*b for r,g,b in colors)/len(colors)
    palette = "Closely matched colors" if (distance+reverse)/2 < 65 else "Distinct color palettes"
    light = "similar brightness" if abs(brightness(a)-brightness(b)) < 35 else "contrasting brightness"
    return f"{palette}, {light}."


def callingcard_card(
    visual: ProfileVisual,
    *,
    nickname: str | None,
    relationship: str,
    titles: tuple[str, ...],
) -> bytes:
    from bot.services.callingcard_archive import render_callingcard

    return _save(render_callingcard(visual, nickname=nickname,
        relationship=relationship, titles=titles))
