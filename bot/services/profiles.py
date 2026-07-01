"""Profile composition logic."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProfileSummary:
    """Display-ready profile information."""

    total_given: int
    total_received: int
    favorite_interaction: str | None
    most_interacted_member_id: int | None
