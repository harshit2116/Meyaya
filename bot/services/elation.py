"""Durable rollback records and bounded rules for temporary channel pranks."""
from pathlib import Path
import json
import os

import discord


TITLES = {
    "minister": "Minister of Snacks",
    "diplomat": "Royal Chaos Diplomat",
    "knight": "Knight of Bad Decisions",
    "jester": "Duke of Dramatic Complaints",
    "advisor": "Suspicious Royal Advisor",
    "rebel": "Tiny Rebellion Leader",
}


def public_chat_channel(channel):
    """Conservative: @everyone itself must be able to read and write here."""
    if not isinstance(channel, discord.TextChannel) or channel.is_news():
        return False
    permissions = channel.permissions_for(channel.guild.default_role)
    return permissions.view_channel and permissions.send_messages


def parse_decree(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(value, dict) or not isinstance(value.get("reply"), str):
        return None
    reply = value["reply"].strip()
    if not reply or len(reply) > 1400:
        return None
    return {
        "reply": reply,
        "appointment": value.get("appointment") if isinstance(value.get("appointment"), str) and value["appointment"] in TITLES else None,
        "convinced": value.get("convinced") is True,
    }


class ElationStore:
    """Local durable state; no expiry before restoration has actually succeeded."""
    def __init__(self, root=None):
        self.root = Path(root) if root else Path(__file__).resolve().parents[2] / "runtime" / "elation"

    def load(self):
        result = {}
        for path in self.root.glob("*.json"):
            # Fail closed on corrupt rollback data instead of silently overwriting it.
            state = json.loads(path.read_text(encoding="utf-8"))
            if str(state["guild_id"]) != path.stem:
                raise ValueError("Elation rollback record has an invalid guild ID")
            result[int(path.stem)] = state
        return result

    def save(self, state):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{int(state['guild_id'])}.json"
        temporary = path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
