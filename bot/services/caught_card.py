"""Local, supersampled CCTV parody cards. No AI or remote scene assets."""

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from io import BytesIO
from secrets import choice

from PIL import Image, ImageDraw, ImageOps

from bot.services.card_renderer import font, lines

SIZE = (960, 640)
SCALE = 2


@dataclass(frozen=True)
class Incident:
    scene: str
    location: str
    incident: str
    evidence: str
    status: str


INCIDENTS = (
    Incident("pantry", "SNACK STORAGE", "Negotiating a midnight treaty with the fridge.", "Three missing puddings. One tiny spoon.", "Escaped. Crumbs recovered."),
    Incident("pantry", "SNACK STORAGE", "Replacing every cookie with a raisin.", "A suspiciously healthy cookie jar.", "Wanted for snack treason."),
    Incident("pantry", "SNACK STORAGE", "Reorganizing the snacks by emotional value.", "Chips labelled: emergency happiness.", "Still defending the system."),
    Incident("arcade", "ARCADE / AFTER HOURS", "Challenging the claw machine to a rematch.", "Seven tokens. Zero plushies.", "Machine remains undefeated."),
    Incident("arcade", "ARCADE / AFTER HOURS", "Trying to pay for a high score with compliments.", "A handwritten IOU to the leaderboard.", "Charm attempt unsuccessful."),
    Incident("arcade", "ARCADE / AFTER HOURS", "Teaching the racing game to respect speed limits.", "A first-place finish in reverse.", "License revoked by a pixel."),
    Incident("server", "SERVER ROOM", "Installing extra RAM using motivational stickers.", "A sticker reading: you got this, bestie.", "Performance unchanged. Morale improved."),
    Incident("server", "SERVER ROOM", "Asking the router to stop buffering dramatically.", "An apology letter addressed to Wi-Fi.", "Router declined to comment."),
    Incident("server", "SERVER ROOM", "Renaming every cable to spaghetti.", "A network diagram with pasta sauce.", "IT has several questions."),
)


def choose_incident():
    return choice(INCIDENTS)


class Canvas:
    def __init__(self, image):
        self.image = image
        self.draw = ImageDraw.Draw(image)

    def box(self, xy, fill, outline=None, radius=0, width=1):
        xy = tuple(round(v * SCALE) for v in xy)
        if radius:
            self.draw.rounded_rectangle(xy, radius=radius * SCALE, fill=fill,
                                        outline=outline, width=width * SCALE)
        else:
            self.draw.rectangle(xy, fill=fill, outline=outline, width=width * SCALE)

    def polygon(self, points, fill):
        self.draw.polygon([(x * SCALE, y * SCALE) for x, y in points], fill=fill)

    def line(self, points, fill, width=1):
        self.draw.line([(x * SCALE, y * SCALE) for x, y in points], fill=fill, width=width * SCALE)

    def ellipse(self, xy, fill, outline=None, width=1):
        self.draw.ellipse(tuple(v * SCALE for v in xy), fill=fill, outline=outline, width=width * SCALE)

    def text(self, xy, text, size=20, fill="#e7f8f4", anchor=None):
        self.draw.text(tuple(v * SCALE for v in xy), text, font=font(size * SCALE), fill=fill, anchor=anchor)


@lru_cache(maxsize=3)
def scene_background(scene):
    image = Image.new("RGB", (SIZE[0] * SCALE, SIZE[1] * SCALE), "#0b151c")
    c = Canvas(image)
    c.box((22, 78, 938, 461), "#142a32")
    c.polygon([(22, 78), (225, 136), (225, 347), (22, 461)], "#10212a")
    c.polygon([(938, 78), (763, 136), (763, 347), (938, 461)], "#1c333a")
    c.box((225, 136, 763, 347), "#223c42")
    c.polygon([(22, 461), (225, 347), (763, 347), (938, 461)], "#15282e")
    for x in range(-300, 1400, 130):
        c.line([(480 + (x - 480) * .4, 347), (x, 461)], "#2a4246")
    for y in (366, 392, 423, 460):
        c.line([(22, y), (938, y)], "#2a4246")
    c.box((430, 98, 566, 108), "#88b4aa", radius=4)
    if scene == "pantry":
        c.box((626, 167, 744, 357), "#263d47", "#91ada8", radius=7, width=2)
        c.line([(626, 229), (744, 229)], "#91ada8", 2)
        c.box((638, 242, 642, 281), "#b6c3b5", radius=2)
        c.box((254, 194, 438, 340), "#23363b", "#688a84", radius=3)
        for y in (230, 275, 321):
            c.box((257, y, 435, y + 5), "#698578")
            for x in (274, 328, 382):
                c.box((x, y - 24, x + 29, y - 2), "#b29758", "#d2bb77", radius=4)
                c.line([(x + 6, y - 17), (x + 22, y - 17)], "#635f43", 2)
        c.text((273, 174), "SNACK INVENTORY", 13, "#a7b9a7")
    elif scene == "arcade":
        for x, accent in ((263, "#85bba6"), (620, "#b39aca")):
            c.polygon([(x, 185), (x + 107, 185), (x + 121, 350), (x - 12, 350)], "#11202c")
            c.box((x + 3, 185, x + 104, 211), "#334f5c", accent, radius=2)
            c.text((x + 53, 199), "PLAY", 14, accent, "mm")
            c.box((x + 10, 219, x + 96, 285), "#294450", accent, radius=4)
            c.line([(x + 24, 270), (x + 44, 244), (x + 64, 263), (x + 82, 237)], accent, 3)
            c.box((x + 2, 295, x + 103, 311), "#54717a")
            c.ellipse((x + 27, 298, x + 36, 307), accent)
    else:
        for x in (254, 634):
            c.box((x, 163, x + 106, 354), "#101e28", "#557c81", radius=5)
            for y in range(184, 332, 24):
                c.box((x + 8, y, x + 98, y + 18), "#2a434e", radius=2)
                for led in range(3):
                    c.ellipse((x + 16 + led * 10, y + 6, x + 20 + led * 10, y + 10), "#8cd4ad")
                c.line([(x + 59, y + 8), (x + 88, y + 8)], "#57777d", 2)
        c.line([(352, 355), (399, 392), (596, 392), (646, 355)], "#769695", 3)
    # Fine camera texture stays behind text/portrait: readability wins over noise.
    texture = Image.effect_noise((916 * SCALE, 383 * SCALE), 12).convert("RGB")
    crop = image.crop((22 * SCALE, 78 * SCALE, 938 * SCALE, 461 * SCALE))
    image.paste(Image.blend(crop, texture, .06), (22 * SCALE, 78 * SCALE))
    return image


def render_caught(name, avatar=b"", incident=None, timestamp=None):
    case = incident or choose_incident()
    if case.scene not in {"pantry", "arcade", "server"}:
        raise ValueError("Unknown caught scene")
    name = " ".join(str(name).split())[:48] or "Member"
    timestamp = timestamp or datetime.now(timezone.utc)
    image = scene_background(case.scene).copy()
    c = Canvas(image)
    # A little illustrated suspect silhouette, not merely a pasted profile circle.
    c.ellipse((434, 401, 571, 432), "#101d23")
    c.line([(487, 347), (466, 410)], "#142431", 20)
    c.line([(516, 347), (539, 410)], "#142431", 20)
    c.box((449, 276, 551, 355), "#425e69", "#688d95", radius=25, width=2)
    c.line([(454, 294), (419, 330)], "#425e69", 18)
    c.line([(547, 294), (581, 315)], "#425e69", 18)
    portrait = Image.new("RGB", (104 * SCALE, 104 * SCALE), "#294552")
    Canvas(portrait).text((52, 52), name[0].upper(), 44, anchor="mm")
    if avatar and len(avatar) <= 1024 * 1024:
        try:
            with Image.open(BytesIO(avatar)) as source:
                if source.width * source.height <= 4_000_000:
                    portrait = ImageOps.fit(source.convert("RGB"), portrait.size, method=Image.Resampling.LANCZOS)
        except (OSError, ValueError):
            pass
    mask = Image.new("L", portrait.size)
    ImageDraw.Draw(mask).ellipse((0, 0, portrait.width - 1, portrait.height - 1), fill=255)
    image.paste(portrait, (448 * SCALE, 178 * SCALE), mask)
    c.ellipse((448, 178, 552, 282), None, "#a9d5cf", 2)
    scanlines = Image.new("RGBA", image.size)
    scan_draw = ImageDraw.Draw(scanlines)
    for y in range(80 * SCALE, 460 * SCALE, 4 * SCALE):
        scan_draw.line((22 * SCALE, y, 938 * SCALE, y), fill=(0, 8, 12, 14), width=SCALE)
    image.paste(scanlines, (0, 0), scanlines)
    # Tracking corners and HUD are deliberately crisp after the camera texture.
    for x, y, dx, dy in ((424, 162, 1, 1), (575, 162, -1, 1), (424, 368, 1, -1), (575, 368, -1, -1)):
        c.line([(x, y + dy * 17), (x, y), (x + dx * 17, y)], "#a6e6cd", 2)
    c.box((22, 18, 71, 54), "#2b4c52", radius=6)
    c.text((46, 36), "03", 19, anchor="mm")
    c.text((84, 19), case.location, 20)
    c.text((85, 45), "MEYAYA / SECURITY ARCHIVE", 10, "#91aaa9")
    c.ellipse((843, 28, 853, 38), "#ee7f83")
    c.text((864, 24), "REC", 17)
    c.text((42, 97), timestamp.astimezone(timezone.utc).strftime("%d %b %Y  %H:%M:%S UTC").upper(), 14, "#c0ded4")
    c.text((917, 433), "FICTIONAL INCIDENT", 11, "#a0b9b4", "ra")
    c.text((38, 485), "SUSPECT", 11, "#7ea4a2")
    # Name and prose are measured before drawing; long names cannot clip the HUD.
    for size in range(23, 5, -1):
        if c.draw.textlength(name, font=font(size * SCALE)) <= 360 * SCALE:
            break
    c.text((38, 507), name, size)
    c.text((420, 485), "INCIDENT REPORT", 11, "#7ea4a2")
    rows = lines(c.draw, case.incident, 20 * SCALE, 500 * SCALE)
    for i, row in enumerate(rows[:2]):
        c.text((420, 506 + i * 25), row, 20)
    c.line([(38, 571), (922, 571)], "#29464c")
    c.text((38, 590), "EVIDENCE", 10, "#7ea4a2")
    c.text((38, 608), case.evidence, 13)
    c.text((922, 590), "STATUS", 10, "#7ea4a2", "ra")
    c.text((922, 608), case.status, 13, "#b5d8c4", "ra")
    output = BytesIO()
    image.resize(SIZE, Image.Resampling.LANCZOS).save(output, format="PNG", compress_level=4)
    return output.getvalue()
