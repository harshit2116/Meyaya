"""Ship service: computes a stable, deterministic love percentage for a pair of users."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date

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
    """Computes ship percentages. No database needed — it's a pure function
    seeded by the pair of user IDs and the current day, so the result stays
    the same for a pair all day but can shift day to day."""

    def ship(self, user_one_id: int, user_two_id: int, *, day: date | None = None) -> ShipResult:
        day = day or date.today()
        a, b = normalize_pair(user_one_id, user_two_id)

        if a == b:
            # Someone shipped themselves.
            return ShipResult(user_a_id=a, user_b_id=b, percentage=100, label="Self love 💖")

        seed_str = f"{a}-{b}-{day.isoformat()}"
        digest = hashlib.sha256(seed_str.encode("utf-8")).hexdigest()
        percentage = int(digest[:8], 16) % 101  # 0-100

        return ShipResult(
            user_a_id=a,
            user_b_id=b,
            percentage=percentage,
            label=_label_for_percentage(percentage),
        )