"""Approved roleplay identities and their ignored private character prompts."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PRIVATE_DIRECTORY = Path(__file__).resolve().parents[1] / "private"


@dataclass(frozen=True, slots=True)
class RoleplayPersona:
    """Public identity metadata for one explicitly fictional roleplay persona."""

    key: str
    display_name: str
    private_prompt_path: Path


ROLEPLAY_PERSONAS: dict[str, RoleplayPersona] = {
    "jungkook": RoleplayPersona(
        key="jungkook",
        display_name="Jungkook RP",
        private_prompt_path=PRIVATE_DIRECTORY / "roleplay_jungkook.txt",
    ),
    "alya": RoleplayPersona(
        key="alya",
        display_name="Alya RP",
        private_prompt_path=PRIVATE_DIRECTORY / "roleplay_alya.txt",
    ),
}

SAFE_ROLEPLAY_FALLBACK = (
    "Portray the selected fictional roleplay identity warmly and consistently. Keep the reply "
    "concise, never claim to be the real person behind the character, and never invent private "
    "real-world facts."
)


@lru_cache(maxsize=len(ROLEPLAY_PERSONAS))
def load_roleplay_prompt(character: str) -> str:
    """Load a private character prompt without making startup depend on the file."""

    persona = ROLEPLAY_PERSONAS[character]
    try:
        prompt = persona.private_prompt_path.read_text(encoding="utf-8").strip()
    except OSError:
        logger.warning("Private roleplay prompt unavailable character=%s", character)
        return SAFE_ROLEPLAY_FALLBACK
    return prompt or SAFE_ROLEPLAY_FALLBACK


def build_roleplay_instruction(character: str, speaker: str) -> str:
    """Build a bounded instruction for an isolated, one-message RP response."""

    return "\n\n".join(
        (
            load_roleplay_prompt(character),
            (
                "This is clearly labelled character roleplay in a Discord server. Stay in "
                "character, but never claim the account is the real public figure or character. "
                "Do not claim access to private information, direct messages, live locations, or "
                "real-world relationships. Do not imitate signatures or request money."
            ),
            (
                f"The current speaker is {speaker}. Respond only to their current message. "
                "Return only the visible in-character reply with no control tags, commands, "
                "memory directives, analysis, or speaker label. Keep it below 180 words and use "
                "normal hyphens instead of long dashes."
            ),
        )
    )
