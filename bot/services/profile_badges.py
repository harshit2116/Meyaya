"""API-visible profile badges with bundled official artwork. No runtime requests."""
from functools import lru_cache
from pathlib import Path
from PIL import Image

PROFILE_BADGES = {
    "staff": "Discord Staff", "partner": "Partner", "hypesquad": "HypeSquad Events",
    "bug_hunter": "Bug Hunter", "bug_hunter_level_2": "Bug Hunter Gold",
    "hypesquad_bravery": "Bravery", "hypesquad_brilliance": "Brilliance",
    "hypesquad_balance": "Balance", "early_supporter": "Early Supporter",
    "early_verified_bot_developer": "Early Bot Developer",
    "discord_certified_moderator": "Moderator Alumni",
}
BADGE_FILES = {label: Path(__file__).resolve().parents[1] / "assets/profile/badges" / (flag + ".png")
               for flag, label in PROFILE_BADGES.items()}

@lru_cache(maxsize=16)
def badge_icon(label):
    path = BADGE_FILES.get(label)
    if path is None:
        return None
    try:
        with Image.open(path) as source:
            return source.convert("RGBA").resize((40, 40), Image.Resampling.LANCZOS)
    except (OSError, ValueError):
        return None
