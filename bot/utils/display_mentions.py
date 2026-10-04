"""Convert Discord mention markup into inert labels for rendered cards."""

import re

MENTION = re.compile(r"<(@!?|@&|#)(\d+)>")


def display_mentions(ctx, text: str) -> str:
    guild = getattr(ctx, "guild", None)
    message = getattr(ctx, "message", None)

    def lookup(obj, method, user_id):
        getter = getattr(obj, method, None)
        return getter(user_id) if getter else None

    def replace(match):
        kind, identifier = match.group(1), int(match.group(2))
        if kind == "#":
            channel = lookup(guild, "get_channel_or_thread", identifier) or lookup(guild, "get_channel", identifier)
            return "#" + (channel.name if channel else "unknown-channel")
        if kind == "@&":
            role = lookup(guild, "get_role", identifier)
            return "@" + (role.name if role else "unknown-role")
        member = lookup(guild, "get_member", identifier)
        if member is None:
            member = next((item for item in getattr(message, "mentions", ()) if item.id == identifier), None)
        if member is None and getattr(getattr(ctx, "author", None), "id", None) == identifier:
            member = ctx.author
        if member is None:
            member = lookup(getattr(ctx, "bot", None), "get_user", identifier)
        return "@" + (member.display_name if member else "unknown-user")

    return MENTION.sub(replace, text)
