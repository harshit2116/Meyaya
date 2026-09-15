"""Fast, fresh ship scoring with varied Meyaya verdicts."""

from __future__ import annotations

from dataclasses import dataclass
from random import SystemRandom

from bot.models.relationship import normalize_pair

_RANDOM = SystemRandom()
MAX_TRACKED_PAIRS = 2000

VERDICTS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (95, ("Written in the stars 💞", "Absolute soulmates 💍", "Unfairly perfect 💖")),
    (
        85,
        (
            "Dangerously compatible 💘",
            "Main-character romance 🌸",
            "A terrifyingly good match 💗",
        ),
    ),
    (
        70,
        (
            "Serious chemistry 💕",
            "This could actually work ✨",
            "The sparks are sparking 💓",
        ),
    ),
    (50, ("Promising potential 💝", "A cute little maybe 🌷", "Worth investigating 👀")),
    (
        30,
        (
            "Chaotic but possible 💟",
            "The plot needs development 🎭",
            "Mixed signals, maximum drama 🍿",
        ),
    ),
    (
        10,
        (
            "A very ambitious ship 🛶",
            "Friend-zone turbulence detected 🌊",
            "Meyaya has concerns 😭",
        ),
    ),
    (
        0,
        (
            "The ship forgot its engine 💔",
            "Besties might be safer 😅",
            "Romance.exe stopped responding 🫠",
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class ShipResult:
    user_a_id: int
    user_b_id: int
    percentage: int
    label: str


def _label_for_percentage(percentage: int) -> str:
    for minimum, labels in VERDICTS:
        if percentage >= minimum:
            return _RANDOM.choice(labels)
    return VERDICTS[-1][1][0]


class ShipService:
    """Generate a new ship roll while preventing immediate pair repeats."""

    def __init__(self) -> None:
        self._last_scores: dict[tuple[int, int], int] = {}

    def ship(self, user_one_id: int, user_two_id: int) -> ShipResult:
        a, b = normalize_pair(user_one_id, user_two_id)
        if a == b:
            return ShipResult(a, b, 100, "Self-love stays undefeated 💖")

        pair = (a, b)
        previous = self._last_scores.get(pair)
        percentage = _RANDOM.randrange(101)
        if percentage == previous:
            percentage = (percentage + _RANDOM.randrange(1, 101)) % 101

        if len(self._last_scores) >= MAX_TRACKED_PAIRS and pair not in self._last_scores:
            self._last_scores.pop(next(iter(self._last_scores)))
        self._last_scores[pair] = percentage

        return ShipResult(
            user_a_id=a,
            user_b_id=b,
            percentage=percentage,
            label=_label_for_percentage(percentage),
        )
