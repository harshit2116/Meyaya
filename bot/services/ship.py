"""Ship service: computes a random love percentage for a pair of users."""

from __future__ import annotations

import random
from dataclasses import dataclass

from bot.models.relationship import normalize_pair


@dataclass(frozen=True)
class ShipResult:
    user_a_id: int
    user_b_id: int
    percentage: int
    label: str


def _label_for_percentage(pct: int) -> str:
    if pct >= 90:
        return "Soulmates 💞"
    if pct >= 70:
        return "Strong match 💘"
    if pct >= 50:
        return "There's something there 💗"
    if pct >= 30:
        return "It's complicated 💔"
    return "Just friends... probably 😅"


class ShipService:
    """Computes ship percentages. Fully random on every call."""

    def ship(self, user_one_id: int, user_two_id: int) -> ShipResult:
        a, b = normalize_pair(user_one_id, user_two_id)

        if a == b:
            return ShipResult(user_a_id=a, user_b_id=b, percentage=100, label="Self love 💖")

        percentage = random.randint(0, 100)

        return ShipResult(
            user_a_id=a,
            user_b_id=b,
            percentage=percentage,
            label=_label_for_percentage(percentage),
        )