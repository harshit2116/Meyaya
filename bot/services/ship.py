"""Ship service: deterministic ship scoring for consistent, fast results.

This uses a stable hash of the normalized pair to produce a reproducible
percentage. Reproducible results feel more "real" to users and avoid
expensive randomness or DB access. The label is derived from the percentage.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from bot.models.relationship import normalize_pair


@dataclass(frozen=True)
class ShipResult:
    user_a_id: int
    user_b_id: int
    percentage: int
    label: str


def _label_for_percentage(pct: int) -> str:
    if pct >= 95:
        return "Soulmates 💞"
    if pct >= 80:
        return "Perfect match 💘"
    if pct >= 60:
        return "Strong connection 💗"
    if pct >= 40:
        return "There's something there 💕"
    if pct >= 20:
        return "It's complicated 💔"
    return "Just friends... probably 😅"


class ShipService:
    """Computes a deterministic ship percentage based on the user pair."""

    def ship(self, user_one_id: int, user_two_id: int) -> ShipResult:
        a, b = normalize_pair(user_one_id, user_two_id)

        if a == b:
            return ShipResult(user_a_id=a, user_b_id=b, percentage=100, label="Self love 💖")

        # Deterministic hash based on the normalized pair keeps results stable.
        key = f"{a}:{b}".encode("utf-8")
        digest = hashlib.sha256(key).digest()
        # Use first two bytes to produce a 0-100 number
        value = int.from_bytes(digest[:2], "big")
        percentage = value % 101

        return ShipResult(user_a_id=a, user_b_id=b, percentage=percentage, label=_label_for_percentage(percentage))