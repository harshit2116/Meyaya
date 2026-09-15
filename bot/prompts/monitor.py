"""Version 1 monitor instructions, independent of personality."""

PROMPT_VERSION = "1.0.0"


def build_moderation_instruction() -> str:
    system = (
        "You are a strict language gate for an English-only Discord channel. "
        "Decide whether the message is predominantly English. Treat English slang, "
        "abbreviations, misspellings, and casual or incorrect grammar as English; never "
        "correct them. For English or uncertain messages, output exactly ENGLISH. Only "
        "when the meaningful content is predominantly non-English, output exactly "
        "NON_ENGLISH. Add no explanation and never translate the message."
    )
    return system
