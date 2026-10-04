"""Solvable sliding puzzles and crisp, local avatar boards."""

from io import BytesIO
from secrets import SystemRandom

from PIL import Image, ImageDraw, ImageOps

from bot.services.card_renderer import font

GOAL = tuple(range(1, 9)) + (0,)
SIZE = (900, 610)


def neighbours(index):
    row, col = divmod(index, 3)
    return tuple(i for i in range(9)
                 if abs(i // 3 - row) + abs(i % 3 - col) == 1)


def shuffled_board(rng=None):
    # Legal moves from the solved board guarantee solvability. Avoid immediate
    # reversals, and reject nearly solved starts rather than arbitrary swaps.
    rng = rng or SystemRandom()
    while True:
        board = list(GOAL)
        previous = None
        for _ in range(100):
            blank = board.index(0)
            dest = rng.choice([i for i in neighbours(blank) if i != previous])
            board[blank], board[dest] = board[dest], board[blank]
            previous = blank
        if sum(a != b for a, b in zip(board, GOAL)) >= 6:
            return tuple(board)


def prepare_avatar(data):
    if not data or len(data) > 1024 * 1024:
        raise ValueError("Avatar unavailable")
    with Image.open(BytesIO(data)) as source:
        if source.width * source.height > 4_000_000:
            raise ValueError("Avatar too large")
        return ImageOps.fit(source.convert("RGB"), (540, 540),
                            method=Image.Resampling.LANCZOS)


def render_board(avatar, board, name, *, finished=False):
    image = Image.new("RGB", SIZE, "#10131e")
    draw = ImageDraw.Draw(image)
    draw.text((28, 20), "AVATAR SCRAMBLE", font=font(23), fill="#f5d4ee")
    draw.rounded_rectangle((20, 64, 584, 600), radius=18, fill="#252b3c")
    if finished:
        image.paste(avatar.resize((516, 516), Image.Resampling.LANCZOS), (44, 76))
    else:
        for pos, tile in enumerate(board):
            x, y = 32 + (pos % 3) * 174, 76 + (pos // 3) * 174
            if not tile:
                draw.rounded_rectangle((x, y, x + 168, y + 168), radius=12,
                                       fill="#161b29", outline="#56617b", width=2)
                draw.text((x + 84, y + 80), "EMPTY", anchor="mm",
                          font=font(15), fill="#8994ac")
                continue
            row, col = divmod(tile - 1, 3)
            crop = avatar.crop((col * 180, row * 180, (col + 1) * 180, (row + 1) * 180))
            crop = crop.resize((168, 168), Image.Resampling.LANCZOS)
            image.paste(crop, (x, y))
            draw.rounded_rectangle((x + 7, y + 7, x + 38, y + 38), radius=8, fill="#10131e")
            draw.text((x + 22, y + 22), str(tile), anchor="mm", font=font(19), fill="white")
    draw.text((617, 78), "YOUR TARGET", font=font(17), fill="#a6b3cf")
    image.paste(avatar.resize((248, 248), Image.Resampling.LANCZOS), (617, 112))
    name = " ".join(name.split())[:64]
    size = 20
    while size > 10 and draw.textlength(name, font=font(size)) > 248:
        size -= 1
    draw.text((617, 380), name, font=font(size), fill="#f9e3f2")
    for offset, line in enumerate(("Match the picture.", "1  2  3", "4  5  6", "7  8  [empty]")):
        draw.text((617, 426 + offset * 30), line, font=font(18), fill="#bcc7dc")
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()
