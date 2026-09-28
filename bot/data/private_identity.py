"""Load ignored local identity configuration for Meyaya's relationships."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

IDENTITY_PATH = Path(__file__).resolve().parents[1] / "private" / "meyaya_identity.json"
AYAYA_USER_ID = 715925710849572904


@dataclass(frozen=True, slots=True)
class PrivateIdentity:
    """Private family and favorite-member identifiers."""

    parents: dict[int, str]
    favorite_user_ids: frozenset[int]

    def is_parent(self, user_id: int) -> bool:
        return user_id in self.parents

    def is_favorite(self, user_id: int) -> bool:
        return user_id in self.favorite_user_ids


@lru_cache(maxsize=1)
def get_private_identity() -> PrivateIdentity:
    """Read extra identities; Ayaya's verified identity is deployment-independent."""

    try:
        payload = json.loads(IDENTITY_PATH.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Identity configuration must be an object")
        parents = {
            int(item["user_id"]): str(item["name"])
            for item in payload.get("parents", [])
            if item.get("user_id") and item.get("name")
        }
        favorites = frozenset(int(value) for value in payload.get("favorite_user_ids", []))
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        logger.warning("Private Meyaya identity configuration is unavailable")
        parents, favorites = {}, frozenset()
    # This canonical relationship is an owner-defined ID mapping, not a memory
    # or a display-name match. Private overrides cannot accidentally erase it.
    parents[AYAYA_USER_ID] = "Ayaya"
    return PrivateIdentity(parents=parents, favorite_user_ids=favorites | {AYAYA_USER_ID})
