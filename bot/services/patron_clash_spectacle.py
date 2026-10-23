"""Authored power-up interludes and bounded, procedural authority animations.

Presentation only: these helpers never touch combat state or its random stream.
"""

from functools import lru_cache
from io import BytesIO
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from bot.services.card_renderer import font

AWAKENINGS = (
    (
        "THE LIMITERS COME OFF",
        "Prismatic Ascension", "Everbloom unfolds into five orbiting blades of light. A crown of petals ignites above Meyaya.",
        "Void Revenant", "Mournfang drinks the colour from the horizon. Veyra steps through the hole it leaves behind.",
        "You brought a world-ending sword? Cute. I brought spare worlds.",
        "Then I will count how many times you can watch one die.",
    ),
    (
        "SECOND AUTHORITY RELEASE",
        "Genesis Sovereign", "Her shattered blades become a constellation. Every fragment carries the blueprint of a new sky.",
        "Sovereign of the Abyss", "A black halo opens behind Veyra. The battlefield folds inward, answering only to Mournfang.",
        "Okay. No more being polite. Everbloom, crown me.",
        "There she is. The god hiding behind the smile.",
    ),
    (
        "TRUE NAMES UNSEALED",
        "Origin Protocol: First Dawn", "The crown breaks into a rising sun. Meyaya draws every remaining petal into one impossible beginning.",
        "Enemy of All: Absolute Erasure", "Her halo collapses to a single crimson edge. Veyra raises the silence that existed before the first word.",
        "I am not protecting a perfect world. I am protecting the chance to make it better.",
        "Then give me everything, Meyaya. Let the last thing I erase be your hesitation.",
    ),
)

CHOREOGRAPHY = {
    "Prism Cascade": (
        "Five petals scatter, turn, and strike from five different tomorrows. Mournfang meets them in a rain of sparks.",
        "Meyaya feints with the first four rays. The fifth curls behind Veyra, carrying a very personal grudge.",
        "Everbloom splits the air into a prism corridor. Light ricochets between its walls before converging on Veyra.",
    ),
    "World Sever": (
        "Veyra draws a line across the horizon. The prismatic guard tears along it, and the cut arrives a heartbeat later.",
        "Mournfang vanishes inside its own shadow. Its edge returns from the far side of Meyaya's shield.",
        "One quiet step. One impossible cut. Behind Veyra, the skyline separates like paper.",
    ),
    "Genesis Crown": (
        "Meyaya catches falling fragments in her crown. They bloom into a ring of lances and descend together.",
        "Everbloom plants a luminous seed in empty space. A cathedral of thorns erupts around Mournfang's path.",
        "The ruined sky becomes her forge. Meyaya brings its newborn constellations down like a royal decree.",
    ),
    "Abyss Dominion": (
        "Veyra closes her hand. The horizon folds toward her, dragging the newborn stars into a soundless storm.",
        "A thousand dark reflections lift Mournfang. Only one is real; every reflection still leaves a cut.",
        "The abyss rises like an inverted ocean. Veyra walks across its surface and lets the whole tide fall.",
    ),
    "Origin Protocol · The First Dawn": (
        "Every scattered petal answers. Meyaya swings a blade made from all the mornings the abyss tried to steal.",
        "The crown shatters on purpose. Each fragment becomes a sunrise; their light converges at Everbloom's tip.",
        "Meyaya steps into the silence and writes one word in light: BEGIN. The battlefield answers in bloom.",
    ),
    "Enemy of All · Absolute Erasure": (
        "All the shadows stop moving. Veyra draws Mournfang through the place where the world's name used to be.",
        "The abyss abandons its shape. One crimson thread remains, and Veyra pulls it through the heart of the dawn.",
        "Veyra lowers the blade. For a breath, even its afterimage disappears. Then the absence reaches Meyaya.",
    ),
}


def choreography_for(state, actor):
    lines = CHOREOGRAPHY.get(actor.last_move)
    return lines[(max(1, actor.skills_used) - 1) % len(lines)] if lines else "The two authorities collide."


def condition_for(fighter):
    """Qualitative dramatic cues; sovereign HP and MP remain hidden."""
    ratio = fighter.hp / max(1, fighter.max_hp)
    return ("On the last heartbeat" if ratio <= .25 else
            "Authority destabilising" if ratio <= .5 else
            "Holding against the fracture" if ratio <= .75 else "Authority unbroken")


@lru_cache(maxsize=6)
def awakening_media(phase, animated):
    """Three reusable, non-flashing sigil sequences, < 15 MiB RGB frame pixels.

    No network, model, per-match randomisation or character-art generation.
    Run via animation_work, never on Discord's event loop.
    """
    if phase not in range(3):
        raise ValueError("Unknown authority phase")
    width, height = 640, 240
    heading = font(17)
    caption = font(12)
    frames = []
    total = 32 if animated else 1
    for index in range(total):
        t = index / (total - 1) if animated else 1
        image = Image.new("RGB", (width, height), "#100d1c")
        draw = ImageDraw.Draw(image)
        for cx, colour, direction in ((165, (243, 178, 220), 1), (475, (255, 97, 126), -1)):
            radius = 48 + phase * 7
            for ring in range(3):
                r = radius + ring * 10 + math.sin(t * math.tau + ring) * 3
                draw.arc((cx-r, 113-r, cx+r, 113+r), t*160*direction+ring*40,
                         t*160*direction+ring*40+240, fill=tuple(int(c/(ring+1)) for c in colour), width=2)
            points = []
            for petal in range(5 + phase * 2):
                angle = petal * math.tau / (5 + phase * 2) + t * 1.4 * direction
                x, y = cx + math.cos(angle)*radius, 113 + math.sin(angle)*radius
                points.append((x, y))
                draw.ellipse((x-4, y-4, x+4, y+4), fill=colour)
            draw.line(points + points[:1], fill=colour, width=2)
            for particle in range(18):
                travel = (t + particle / 18) % 1
                angle = particle * 2.39996 + phase
                r = 25 + travel * 76
                x, y = cx + math.cos(angle)*r, 113 + math.sin(angle)*r
                shade = tuple(int(c * (1-travel)*.65) for c in colour)
                draw.ellipse((x-1, y-1, x+1, y+1), fill=shade)
            draw.text((cx, 105), "ORIGIN" if direction == 1 else "ERASURE", font=heading, fill=colour, anchor="mm")
        draw.text((320, 17), AWAKENINGS[phase][0], font=heading, fill="#fff0fa", anchor="mt")
        draw.text((320, 213), f"AUTHORITY RELEASE  {phase+1} / 3", font=caption, fill="#c4a7ee", anchor="mt")
        # A slow converging seam, rather than a screen-wide flash or shake.
        spread = 30*(1-t)
        draw.line((320-spread, 60, 320+spread, 177), fill="#c4a7ee", width=2)
        frames.append(image)
    output = BytesIO()
    if animated:
        frames[0].save(output, "GIF", save_all=True, append_images=frames[1:],
                       duration=100, loop=0, disposal=2, optimize=False)
    else:
        frames[0].save(output, "JPEG", quality=88)
    data = output.getvalue()
    if len(data) > 1_000_000:
        raise ValueError("Authority animation exceeds upload budget")
    return data, f"clash-awakening-{phase}.{'gif' if animated else 'jpg'}"


def victory_animation(path, origin):
    """Animate the existing illustrated ending with petals or falling void sparks."""
    with Image.open(path) as source:
        base = ImageOps.fit(source.convert("RGB"), (640, 280))
    # One palette for the entire scene avoids 30 expensive adaptive quantisations
    # and lets the GIF encoder store only the moving particle rectangles.
    palette = base.quantize(colors=128, method=Image.Quantize.FASTOCTREE)
    frames = []
    colour = (243, 178, 220) if origin else (255, 97, 126)
    for index in range(30):
        image = base.copy()
        overlay = Image.new("RGBA", image.size)
        draw = ImageDraw.Draw(overlay)
        t = index / 30
        for particle in range(28):
            x = (particle * 97 + math.sin(t * math.tau + particle) * 13) % 640
            y = ((particle * 43 + t * 280 * (-1 if origin else 1)) % 280)
            opacity = int(75 + 65 * math.sin(particle + t*math.tau)**2)
            draw.ellipse((x-3, y-2, x+3, y+2), fill=(*colour, opacity))
        image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
        frames.append(image.quantize(palette=palette, dither=Image.Dither.NONE))
    output = BytesIO()
    frames[0].save(output, "GIF", save_all=True, append_images=frames[1:],
                   duration=100, loop=0, disposal=1, optimize=True)
    if output.tell() > 3_000_000:
        raise ValueError("Victory animation exceeds upload budget")
    return output.getvalue()


@lru_cache(maxsize=2)
def dungeon_clash_opening(animated):
    """The story duel begins outside the destroyed prison, with its own artwork."""
    path = Path(__file__).resolve().parents[1] / "assets/fantasy/dungeon/cinematic/final-duel.jpg"
    if animated:
        return victory_animation(path, True), "dungeon-clash.gif"
    return path.read_bytes(), "dungeon-clash.jpg"
