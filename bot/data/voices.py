"""Supported Gemini Live prebuilt voices."""

from __future__ import annotations


GEMINI_LIVE_VOICES = (
    "Zephyr",
    "Puck",
    "Charon",
    "Kore",
    "Fenrir",
    "Leda",
    "Orus",
    "Aoede",
    "Callirrhoe",
    "Autonoe",
    "Enceladus",
    "Iapetus",
    "Umbriel",
    "Algieba",
    "Despina",
    "Erinome",
    "Algenib",
    "Rasalgethi",
    "Laomedeia",
    "Achernar",
    "Alnilam",
    "Schedar",
    "Gacrux",
    "Pulcherrima",
    "Achird",
    "Zubenelgenubi",
    "Vindemiatrix",
    "Sadachbia",
    "Sadaltager",
    "Sulafat",
)

_VOICE_BY_CASEFOLD = {voice.casefold(): voice for voice in GEMINI_LIVE_VOICES}


def canonical_voice_name(value: str) -> str | None:
    """Return the official capitalization for a supported voice name."""

    return _VOICE_BY_CASEFOLD.get(value.strip().casefold())

