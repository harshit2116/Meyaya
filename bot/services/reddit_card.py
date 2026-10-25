"""Local Reddit thread parody with bounded text and reusable vector icons."""
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps
from bot.services.card_renderer import font, lines

BACKGROUND = "#0e1113"
INK = "#eef1f3"
MUTED = "#99adba"
PILL = "#222b30"
ORANGE = "#ff5918"


def subreddit_name(server):
    name = "".join(c for c in str(server) if c.isalnum() or c == "_")[:60]
    return "r/Ask" + (name or "Server")


@lru_cache(maxsize=8)
def _bold(size):
    for path in ("C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return font(size)


def _portrait(image, draw, data, x, y, size, initials):
    draw.ellipse((x, y, x + size, y + size), fill=PILL)
    draw.text((x + size / 2, y + size / 2), initials, font=font(32), fill=INK, anchor="mm")
    if not data or len(data) > 1024 * 1024:
        return
    try:
        with Image.open(BytesIO(data)) as source:
            if source.width * source.height > 4_000_000:
                return
            source.thumbnail((128, 128))
            art = ImageOps.fit(source.convert("RGB"), (size, size))
        mask = Image.new("L", (size * 3, size * 3))
        ImageDraw.Draw(mask).ellipse((0, 0, size * 3 - 1, size * 3 - 1), fill=255)
        image.paste(art, (x, y), mask.resize((size, size), Image.Resampling.LANCZOS))
    except (OSError, ValueError):
        pass


@lru_cache(maxsize=24)
def _icon(kind, color=INK, size=38):
    # Draw once at 3x resolution for clean outlines without external assets.
    mask = Image.new("RGBA", (144, 144))
    d = ImageDraw.Draw(mask)
    def line(points, width=3):
        d.line([(int(x * 3), int(y * 3)) for x, y in points], fill=color, width=width * 3, joint="curve")
    if kind in ("up", "down", "voted"):
        points = [(6, 23), (24, 4), (42, 23), (31, 23), (31, 44), (17, 44), (17, 23), (6, 23)]
        if kind == "down":
            points = [(x, 48-y) for x, y in points]
        if kind == "voted":
            d.polygon([(x*3, y*3) for x,y in points], fill=color)
        else:
            line(points)
    elif kind == "chat":
        d.ellipse((18, 12, 129, 123), outline=color, width=8)
        line([(13, 35), (7, 44), (24, 40)])
    elif kind == "share":
        line([(5, 40), (8, 24), (28, 13), (28, 4), (44, 20), (28, 35), (28, 26), (15, 29), (5, 40)])
    elif kind == "award":
        d.ellipse((24, 6, 117, 105), outline=color, width=8)
        line([(13, 30), (6, 44), (17, 40), (22, 47), (26, 34)])
        line([(32, 29), (42, 44), (31, 40), (27, 47), (23, 35)])
    elif kind == "dots":
        for x in (8, 24, 40):
            d.ellipse((x*3, 65, x*3+12, 77), fill=color)
    return mask.resize((size, size), Image.Resampling.LANCZOS)


def _stamp(image, kind, x, y, color=INK, size=38):
    art = _icon(kind, color, size)
    image.paste(art, (x, y), art)


def _count(value):
    value = max(0, min(999999, int(value)))
    return f"{value / 1000:.1f}K" if value >= 1000 else str(value)


def _fit(draw, text, face, width):
    while text and draw.textlength(text, font=face) > width:
        text = text[:-1]
    return text


def _actions(image, draw, x, y, votes):
    _stamp(image, "voted", x, y, ORANGE)
    draw.text((x+61, y+3), _count(votes), font=font(30), fill=INK)
    _stamp(image, "down", x+163, y)
    for kind, text, dx in (("chat", "Reply", 263), ("award", "Award", 459), ("share", "Share", 664)):
        _stamp(image, kind, x+dx, y)
        draw.text((x+dx+55, y+5), text, font=font(28), fill=INK)
    _stamp(image, "dots", x+862, y, size=34)


def render_reddit(server, username, post, comment="", author_avatar=b"", meyaya_avatar=b"",
                  votes=3200, replies=1900, *, op_comment="", server_icon=b"",
                  comment_votes=1200, op_votes=642):
    username = " ".join(str(username).split())[:50] or "member"
    post = " ".join(str(post).split())[:300]
    comment = " ".join(str(comment).split())[:400]
    op_comment = " ".join(str(op_comment).split())[:400] if comment else ""
    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    post_rows = lines(measure, post, 46, 1180)
    comment_rows = lines(measure, comment, 38, 1040) if comment else []
    op_rows = lines(measure, op_comment, 38, 1000) if op_comment else []
    pills_y = 194 + len(post_rows)*57 + 43
    divider_y = pills_y + 118
    comment_y = divider_y + 92
    actions_y = comment_y + 76 + len(comment_rows)*51 + 34
    op_y = actions_y + 90
    op_actions_y = op_y + 76 + len(op_rows)*51 + 34
    height = (op_actions_y+104 if op_rows else actions_y+104 if comment_rows else divider_y+48)
    image = Image.new("RGB", (1300, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((20, 26, 1280, height-26), radius=20, outline="#344149", width=1)
    _portrait(image, draw, server_icon, 56, 54, 108, str(server).strip()[:1].upper() or "S")
    draw.text((193, 64), _fit(draw, subreddit_name(server), _bold(44), 970), font=_bold(44), fill=INK)
    draw.text((200, 123), f"u/{username}  ·  just now", font=font(31), fill=MUTED)
    _stamp(image, "dots", 1184, 65, MUTED, 40)
    # Match bold Reddit headlines while measuring wrapping at the same size.
    y = 194
    # Reserve a little extra width for bold glyphs before drawing.
    for row in post_rows:
        face = _bold(46)
        while draw.textlength(row, font=face) > 1180:
            face = _bold(face.size-1)
        draw.text((58, y), row, font=face, fill=INK)
        y += 57
    for left, right in ((58,329), (350,555), (576,784)):
        draw.rounded_rectangle((left,pills_y,right,pills_y+77), radius=39, fill=PILL)
    _stamp(image, "up", 89, pills_y+18)
    draw.text((148,pills_y+20), _count(votes), font=font(32), fill=INK)
    draw.line((239,pills_y+23,239,pills_y+55), fill="#64737d", width=2)
    _stamp(image,"down",266,pills_y+18)
    _stamp(image,"chat",381,pills_y+18)
    draw.text((442,pills_y+20),_count(replies) if comment else "0",font=font(32),fill=INK)
    _stamp(image,"share",609,pills_y+18)
    draw.text((668,pills_y+20),"Share",font=font(32),fill=INK)
    draw.line((58,divider_y,1241,divider_y),fill="#344149",width=2)
    if comment:
        draw.text((58,divider_y+25),"Top comment",font=font(34),fill=MUTED)
        draw.line((289,divider_y+42,300,divider_y+53,310,divider_y+42),fill=MUTED,width=3)
        _portrait(image,draw,meyaya_avatar,58,comment_y,94,"M")
        draw.text((178,comment_y+15),"u/Meyaya",font=_bold(34),fill=INK)
        badge_x = 178 + int(draw.textlength("u/Meyaya",font=_bold(34))) + 24
        draw.rounded_rectangle((badge_x,comment_y+17,badge_x+76,comment_y+55),radius=13,fill="#ff9fce")
        draw.text((badge_x+12,comment_y+20),"APP",font=_bold(26),fill=BACKGROUND)
        draw.text((badge_x+99,comment_y+20),"·  just now",font=font(29),fill=MUTED)
        for index,row in enumerate(comment_rows):
            draw.text((178,comment_y+76+index*51),row,font=font(38),fill=INK)
        draw.line((104,comment_y+116,104,actions_y+76),fill="#50616b",width=2)
        _actions(image,draw,178,actions_y,comment_votes)
    if op_comment:
        _portrait(image,draw,author_avatar,98,op_y,90,"U")
        handle = _fit(draw,"u/"+username,_bold(34),650)
        draw.text((218,op_y+15),handle,font=_bold(34),fill=INK)
        badge_x = 218 + int(draw.textlength(handle,font=_bold(34))) + 20
        draw.text((badge_x,op_y+20),"OP",font=_bold(26),fill="#6da9ff")
        draw.text((badge_x+65,op_y+20),"·  just now",font=font(29),fill=MUTED)
        for index,row in enumerate(op_rows):
            draw.text((218,op_y+76+index*51),row,font=font(38),fill=INK)
        draw.line((146,op_y+114,146,op_actions_y+52),fill="#50616b",width=2)
        _actions(image,draw,218,op_actions_y,op_votes)
    output = BytesIO()
    image.save(output,format="PNG",compress_level=1)
    return output.getvalue()
