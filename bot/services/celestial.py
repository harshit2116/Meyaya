"""Versioned daily draws and local celestial PNG rendering, without model dependencies."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
from random import Random


@dataclass(frozen=True)
class CardResult:
    kind: str
    day: str
    title: str
    fields: tuple[tuple[str, str], ...]
    panels: tuple[tuple[str, str, str], ...] = ()
    guild_id: int = 0
    user_id: int = 0
    rules_version: int = 1
    seed: str = ""
    selected_ids: tuple[str, ...] = ()


@lru_cache(maxsize=1)
def definitions():
    root = Path(__file__).resolve().parents[1] / "data" / "cards"
    packs = {
        name: json.loads((root / f"{name}.json").read_text("utf-8"))
        for name in ("tarot", "fortunes", "archetypes", "classes", "guardians")
    }
    if any(pack["version"] != 1 for pack in packs.values()):
        raise ValueError("Unsupported card rules version")
    return {
        **packs["fortunes"],
        "tarot": [[r[k] for k in ("name", "upright", "reversed")] for r in packs["tarot"]["cards"]],
        "archetypes": [
            [r[k] for k in ("title", "path", "strength", "outcome", "meaning", "guidance")]
            for r in packs["archetypes"]["archetypes"]
        ],
        "classes": [
            [r[k] for k in ("title", "role", "affinity", "passive", "drawback")]
            for r in packs["classes"]["classes"]
        ],
        "guardians": [
            [r[k] for k in ("title", "type", "blessing", "weakness")]
            for r in packs["guardians"]["guardians"]
        ],
        "stat_range": packs["classes"]["stat_range"],
        "characters": {r["title"]: r for r in packs["classes"]["classes"]},
        "rarity_weights": packs["classes"]["rarity_weights"],
    }


def draw_card(kind, guild_id, user_id, *, day=None, question=""):
    data = definitions()
    day = day or datetime.now(UTC).date().isoformat()
    seed = f"{data['version']}:{kind}:{guild_id}:{user_id}:{day}"
    rng = Random(int.from_bytes(sha256(seed.encode()).digest(), "big"))
    fields, panels = [], []
    if kind == "fortune":
        title = rng.choice(data["verdicts"])
        luck = rng.randint(1, 100)
        theme = rng.choice(data["themes"])
        if luck >= 76:
            outlook = f"Momentum is strong today. Follow your {theme} instinct, but leave room for one pleasant surprise."
        elif luck >= 46:
            outlook = f"A balanced day rewards steady choices. Let {theme} guide one decision instead of rushing everything."
        else:
            outlook = f"Move gently and protect your energy. Today's focus is {theme}; small steps are enough."
        # All interpretive copy comes from the same score band, not independent rolls.
        if luck >= 76:
            titles = ("A little courage goes a long way", "Make room for a bright surprise", "The wind is at your back")
            omens = ("An invitation opens a promising door.", "A small success gives you fresh momentum.")
            advice = ("Take one thoughtful step toward something you want.", "Share your idea while the spark is fresh.")
        elif luck >= 46:
            titles = ("Good things at your own pace", "A steady hand, a softer day", "Find the magic in the ordinary")
            omens = ("A familiar routine brings an unexpected smile.", "A conversation helps one piece fall into place.")
            advice = ("Finish one small thing before starting another.", "Leave a little room in your plans for a detour.")
        else:
            titles = ("A softer pace is still progress", "Protect your peace today", "Small steps count today")
            omens = ("A delay gives you a useful moment to reconsider.", "A quiet break helps you see things more clearly.")
            advice = ("Choose the manageable task and let the rest wait.", "Pause before committing; you do not need to rush.")
        title = rng.choice(titles)
        fields = [
            ("Luck", f"{luck}/100"),
            ("Lucky number", str(rng.randint(1, 99))),
            ("Color", rng.choice(data["colors"])),
            ("Lucky theme", theme),
            ("Outlook", outlook),
            ("Omen", rng.choice(omens)),
            ("Advice", rng.choice(advice)),
        ]
        if question.strip():
            q_rng = Random(
                int.from_bytes(
                    sha256((seed + question.strip().casefold()).encode()).digest(), "big"
                )
            )
            fields.append(
                (
                    "Question oracle",
                    q_rng.choice(
                        [
                            "A cautious yes - take a small step.",
                            "Not yet - let the idea settle.",
                            "Try another approach.",
                            "Ask for help before deciding.",
                        ]
                    ),
                )
            )
    elif kind == "tarot":
        title = "Past / Present / Future"
        for position, card in zip(("Past", "Present", "Future"), rng.sample(data["tarot"], 3)):
            reversed_card = rng.choice([False, True])
            panels.append(
                (
                    position,
                    card[0] + (" (R)" if reversed_card else ""),
                    card[2] if reversed_card else card[1],
                )
            )
        fields = [("Reading", "Reflect on the past, choose in the present, imagine the future.")]
    elif kind == "fate":
        title, path, strength, outcome, meaning, guidance = rng.choice(data["archetypes"])
        fields = [
            ("Path", path),
            ("Strength", strength),
            ("Meaning", meaning),
            ("Possible chapter", outcome),
            ("Guidance", guidance),
            ("Omen", rng.choice(data["omens"])),
        ]
    elif kind == "summon":
        title, role, affinity, passive, drawback = rng.choice(data["classes"])
        character = data["characters"][title]
        stars = rng.choices([3, 4, 5], weights=data["rarity_weights"])[0]
        fields = [
            ("Rarity", str(stars) + " stars"),
            ("Role", role),
            ("Affinity", affinity),
            (
                "Power / Guard / Spirit",
                " / ".join(str(rng.randint(*data["stat_range"]) + stars * 8) for _ in range(3)),
            ),
            ("Passive", passive),
            ("Shadow", drawback),
            ("Hero", character["name"]),
            ("Signature", character["ultimate"]),
        ]
    elif kind == "guardian":
        title, role, blessing, weakness = rng.choice(data["guardians"])
        fields = [
            ("Type", role),
            ("Affinity", rng.choice(["Lunar", "Starlight", "Forest", "Wind"])),
            ("Bond", str(rng.randint(50, 100)) + "/100"),
            ("Blessing", blessing),
            ("Weakness", weakness),
        ]
    else:
        raise ValueError("Unknown card kind")
    if kind == "tarot":
        selected = tuple(
            f"major_{[r[0] for r in data['tarot']].index(p[1].removesuffix(' (R)')):02d}"
            for p in panels
        )
    elif kind in ("summon", "guardian", "fate"):
        group, prefix = {
            "summon": ("classes", "class"),
            "guardian": ("guardians", "guardian"),
            "fate": ("archetypes", "path"),
        }[kind]
        selected = (f"{prefix}_{[r[0] for r in data[group]].index(title)}",)
    else:
        selected = (f"fortune_{'high' if luck >= 76 else 'steady' if luck >= 46 else 'gentle'}_{titles.index(title)}",)
    return CardResult(
        kind,
        day,
        title,
        tuple(fields),
        tuple(panels),
        guild_id,
        user_id,
        data["version"],
        seed,
        selected,
    )


def render_card(*args, **kwargs):
    """Compatibility entry point; renderer is imported only when presentation is requested."""
    from bot.services.card_renderer import render_card as render

    return render(*args, **kwargs)
