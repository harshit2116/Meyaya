"""Two authored patrons; alignment is a layer over the saved core identity."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

ALIGNMENT_ART = Path(__file__).resolve().parents[1] / "assets" / "duels" / "origin-erasure.png"


@dataclass(frozen=True)
class Patron:
    name: str
    subtitle: str
    icon: str
    oath: str
    resonance: str
    effect: str
    color: str
    dark: str
    lore: str
    titles: tuple[str, ...]


PATRONS = {
    "meyaya": Patron(
        "Meyaya",
        "Bloom of Origin",
        "🌸",
        "Origin Protocol",
        "Origin Resonance",
        "First exchange: Prismatic Guard shields 4% max HP. Healing restores 10% more HP.",
        "#ffbddb",
        "#291d31",
        "Where this soul blooms, possibility answers gently.",
        (
            "Warden of the Prismatic Promise",
            "Bearer of the First Bloom",
            "Keeper of the Gentle Dawn",
        ),
    ),
    "veyra": Patron(
        "Veyra",
        "Enemy of All",
        "🩸",
        "Erasure Active",
        "Erasure Resonance",
        "First landed strike: Erasure Trace deals 1.5% max HP for two round ends. The first two landed strikes weaken remaining shields by 15%.",
        "#ff617e",
        "#200d17",
        "Where this soul walks, certainty begins to fracture.",
        ("Keeper of the Broken Hour", "Warden of the Ruined Promise", "Bearer of the Last Silence"),
    ),
}


def patron_for(profile):
    if getattr(profile, "is_meyaya_boss", False):
        return None
    return PATRONS.get(getattr(profile, "alignment", ""))


def alignment_values(profile, choice):
    patron = PATRONS[choice]
    index = int.from_bytes(sha256(profile.class_id.encode()).digest()[:2], "big") % len(
        patron.titles
    )
    comment = (
        f"A {profile.class_name}? I knew you were hiding main-character problems. Let's make this life bloom."
        if choice == "meyaya"
        else f"A {profile.class_name}. Good. Keep your promise - even when the world breaks first."
    )
    return dict(alignment=choice, fantasy_title=patron.titles[index], meyaya_reaction=comment)
