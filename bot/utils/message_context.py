"""Read bounded, public text from received Discord Components V2 messages."""

import re
from discord.components import Component

_EMOJI_RUN = re.compile(r"(?P<emoji><a?:[A-Za-z0-9_]+:[0-9]+>)(?P=emoji)*")


def compact_component_text(text):
    def compact(match):
        emoji = match["emoji"]
        name = emoji.split(":")[1]
        count = len(match[0]) // len(emoji)
        return f" :{name}:" + (f" ×{count} " if count > 1 else " ")
    return " ".join(_EMOJI_RUN.sub(compact, text).split())


def component_message_text(components, *, limit=1200):
    """Walk wire components, excluding URLs, custom IDs, and spoiler media."""
    if not isinstance(components, (list, tuple)) or limit <= 0:
        return ""
    parts = []
    remaining = limit
    visited = 0

    def append(text):
        nonlocal remaining
        if not isinstance(text, str) or remaining <= 0:
            return
        text = compact_component_text(text)
        if not text:
            return
        if len(text) > remaining:
            text = text[:max(0, remaining - 3)].rstrip() + "..."
        parts.append(text)
        remaining -= len(text) + 1

    def walk(component, depth=0):
        nonlocal visited
        if visited >= 100 or depth > 8 or remaining <= 0:
            return
        visited += 1
        if isinstance(component, Component):
            component = component.to_dict()
        if not isinstance(component, dict) or component.get("spoiler"):
            return
        kind = component.get("type")
        if kind == 10:
            append(component.get("content"))
        elif kind in {9, 17, 1}:
            for child in component.get("components", ()):
                walk(child, depth + 1)
            if kind == 9:
                walk(component.get("accessory"), depth + 1)
        elif kind == 2:
            label = component.get("label")
            if label:
                append(f"action: {label}")
        elif kind == 11:
            append(component.get("description"))
        elif kind == 12:
            for item in component.get("items", ())[:10]:
                if not item.get("spoiler"):
                    description = item.get("description")
                    append(f"image description: {description}" if description else
                           "image: present (visual contents not available as text)")

    for component in components[:40]:
        walk(component)
    return " ".join(parts)[:limit]
