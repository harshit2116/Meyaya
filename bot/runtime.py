"""Restore private config from deployment secrets on each ephemeral boot."""

import json
import os
from pathlib import Path


def restore_private_config():
    raw = os.getenv("MEYAYA_PRIVATE_CONFIG_JSON")
    if not raw:
        return
    values = json.loads(raw)
    if not isinstance(values, dict) or len(raw) > 500_000:
        raise ValueError("Invalid MEYAYA_PRIVATE_CONFIG_JSON")
    root = Path(__file__).resolve().parent / "private"
    allowed = {
        "gemini_persona.txt",
        "gemini_voice_rules.txt",
        "meyaya_identity.json",
        "personality.v1.json",
        "roleplay_alya.txt",
        "roleplay_jungkook.txt",
    }
    targets = []
    for name, content in values.items():
        path = Path(name)
        if not isinstance(content, str) or path.is_absolute() or ".." in path.parts:
            raise ValueError("Invalid private config entry")
        if name not in allowed and not (
            len(path.parts) == 3
            and path.parts[:2] == ("prompt_rules", "v1")
            and path.suffix == ".txt"
        ):
            raise ValueError("Unsupported private config file")
        destination = (root / path).resolve()
        if not destination.is_relative_to(root.resolve()):
            raise ValueError("Private config must remain inside bot/private")
        targets.append((destination, content))
    for destination, content in targets:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        destination.chmod(0o600)
