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

# Official prebuilt voice descriptions; Live uses these studio voices.
VOICE_DESCRIPTIONS = dict(
    zip(
        GEMINI_LIVE_VOICES,
        (
            "Bright",
            "Upbeat",
            "Informative",
            "Firm",
            "Excitable",
            "Youthful",
            "Firm",
            "Breezy",
            "Easy-going",
            "Bright",
            "Breathy",
            "Clear",
            "Easy-going",
            "Smooth",
            "Smooth",
            "Clear",
            "Gravelly",
            "Informative",
            "Upbeat",
            "Soft",
            "Firm",
            "Even",
            "Mature",
            "Forward",
            "Friendly",
            "Casual",
            "Gentle",
            "Lively",
            "Knowledgeable",
            "Warm",
        ),
    )
)


def canonical_voice_name(value: str) -> str | None:
    """Return the official capitalization for a supported voice name."""

    return _VOICE_BY_CASEFOLD.get(value.strip().casefold())
