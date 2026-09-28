"""Read-only server metadata; never enumerate the full member roster."""
from datetime import UTC, datetime


def snowflake_date(value):
    return datetime.fromtimestamp(((int(value) >> 22) + 1420070400000) / 1000, UTC).isoformat()


def rest_server_info(data, channels=None, owner=None):
    """Normalize REST metadata, preserving unavailable values as null."""
    owner_user = (owner or {}).get("user", owner or {})
    roles = data.get("roles")
    info = {
        "id": str(data["id"]), "name": data.get("name"),
        "description": data.get("description"),
        "owner_id": str(data["owner_id"]) if data.get("owner_id") else None,
        "owner_name": (owner or {}).get("nick") or owner_user.get("global_name") or owner_user.get("username"),
        "owner_username": owner_user.get("username"),
        "created_at": snowflake_date(data["id"]),
        "members": data.get("approximate_member_count"),
        "members_approximate": True,
        "online_members": data.get("approximate_presence_count"),
        "locale": data.get("preferred_locale"),
        "features": sorted(data.get("features", [])),
        "vanity_code": data.get("vanity_url_code"),
        "roles": None if roles is None else [
            {"id": str(r["id"]), "name": r["name"], "color": f'#{r.get("color", 0):06x}',
             "position": r.get("position", 0), "managed": r.get("managed", False),
             "mentionable": r.get("mentionable", False)} for r in roles],
        "channels": None if channels is None else [
            {"id": str(c["id"]), "name": c.get("name", "Unnamed"), "type": c.get("type"),
             "category_id": c.get("parent_id"), "nsfw": c.get("nsfw", False),
             "slowmode": c.get("rate_limit_per_user", 0), "position": c.get("position", 0)} for c in channels],
    }
    for key in ("icon", "banner", "splash"):
        asset = data.get(key)
        folder = {"icon": "icons", "banner": "banners", "splash": "splashes"}[key]
        extension = "gif" if asset and asset.startswith("a_") else "png"
        info[f"{key}_url"] = f'https://cdn.discordapp.com/{folder}/{data["id"]}/{asset}.{extension}?size=512' if asset else None
    return info


def cached_server_info(guild):
    """Use the hosted gateway cache without any Discord REST requests."""
    owner = guild.owner
    data = {"id": str(guild.id), "name": guild.name, "owner_id": guild.owner_id,
            "roles": [{"id": str(r.id), "name": r.name, "color": r.color.value,
                       "position": r.position, "managed": r.managed, "mentionable": r.mentionable} for r in guild.roles]}
    for field, attr in {
        "description": "description", "preferred_locale": "preferred_locale",
        "features": "features", "vanity_url_code": "vanity_url_code",
        "approximate_presence_count": "approximate_presence_count",
    }.items():
        value = getattr(guild, attr, None)
        data[field] = getattr(value, "value", value)
    channels = [{"id": str(c.id), "name": c.name, "type": c.type.value,
                 "parent_id": str(c.category_id) if c.category_id else None,
                 "nsfw": getattr(c, "nsfw", False), "rate_limit_per_user": getattr(c, "slowmode_delay", 0),
                 "position": c.position} for c in guild.channels]
    owner_data = {"nick": owner.display_name, "user": {"username": owner.name}} if owner else None
    info = rest_server_info(data, channels, owner_data)
    info.update(members=guild.member_count, members_approximate=False,
                available=not guild.unavailable, source="gateway cache",
                bot_joined_at=guild.me.joined_at.isoformat() if guild.me and guild.me.joined_at else None,
                bot_permissions=[name for name, enabled in guild.me.guild_permissions if enabled] if guild.me else None)
    for key in ("icon", "banner", "splash"):
        asset = getattr(guild, key, None)
        info[f"{key}_url"] = str(asset.url) if asset else None
    return info


def rest_member_preview(rows, roles):
    """Return at most 50 display-only member records, not full Discord payloads."""
    role_names = {str(role['id']): role['name'] for role in roles or []}
    return [{
        'id': str(row['user']['id']),
        'name': row.get('nick') or row['user'].get('global_name') or row['user']['username'],
        'username': row['user']['username'], 'bot': bool(row['user'].get('bot')),
        'joined_at': row.get('joined_at'),
        'roles': [role_names.get(str(role), str(role)) for role in row.get('roles', [])],
    } for row in rows[:50]]


def cached_member_preview(members):
    return [{
        'id': str(member.id), 'name': member.display_name, 'username': member.name,
        'bot': member.bot, 'joined_at': member.joined_at.isoformat() if member.joined_at else None,
        'roles': [role.name for role in member.roles if role.id != member.guild.id],
    } for member in members[:50]]
