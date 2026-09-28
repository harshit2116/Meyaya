"""Deterministic content checks and permission-safe lockdown recovery."""

import asyncio
from datetime import UTC, datetime, timedelta
from collections import deque
import hashlib
import re
import time
from urllib.parse import urlsplit
from weakref import WeakValueDictionary
import discord
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from bot.models.moderation import ChannelLock, ModerationSettings

INVITE = re.compile(
    r"(?<![\w.-])(?:https?://)?(?:www\.)?(?:discord\.gg/|discord(?:app)?\.com/invite/)([A-Za-z0-9-]+)",
    re.I,
)
LINK = re.compile(r"(?:https?://|www\.|discord\.gg/)", re.I)
LOCK_FIELDS = (
    "send_messages",
    "send_messages_in_threads",
    "create_public_threads",
    "create_private_threads",
    "add_reactions",
)


def on_probation(joined_at, now=None):
    return joined_at is not None and (now or datetime.now(UTC)) - joined_at < timedelta(days=3)


def probation_blocked_link(content):
    """Allow only Klipy hosts; one allowed URL never exempts other links."""
    for match in LINK.finditer(content):
        token = re.split(r'[\s<>"\']', content[match.start():], maxsplit=1)[0]
        token = token.rstrip('.,;:!?)]}')
        try:
            parsed = urlsplit(token if token.lower().startswith(('http://', 'https://'))
                              else 'https://' + token)
            host = (parsed.hostname or '').lower()
            if host != 'klipy.com' and not host.endswith('.klipy.com'):
                return True
        except ValueError:
            return True
    return False


class SpamWindow:
    def __init__(self):
        self.entries = {}

    def record(self, guild_id, user_id, channel_id, fingerprints, now=None):
        now = time.monotonic() if now is None else now
        for key, entries in list(self.entries.items()):
            if not entries or now - entries[-1][0] > 60:
                self.entries.pop(key, None)
        repeated = False
        for fingerprint in fingerprints:
            key = (guild_id, user_id, fingerprint)
            entries = self.entries.setdefault(key, deque(maxlen=20))
            while entries and now - entries[0][0] > 60:
                entries.popleft()
            entries.append((now, channel_id))
            repeated |= len({item[1] for item in entries}) >= 3
        # Bound memory even during deliberate bursts of unique content.
        while len(self.entries) > 10000:
            self.entries.pop(next(iter(self.entries)))
        return repeated


def text_fingerprint(text):
    normalized = " ".join(text.casefold().split())
    return hashlib.sha256(normalized.encode()).hexdigest() if len(normalized) >= 12 else None


def snapshot_for(channel):
    targets = dict(channel.overwrites)
    targets.setdefault(channel.guild.default_role, discord.PermissionOverwrite())
    targets.setdefault(channel.guild.me, channel.overwrites_for(channel.guild.me))
    result = {}
    for target, overwrite in targets.items():
        fields = {
            name: getattr(overwrite, name)
            for name in LOCK_FIELDS
            if target.id in {channel.guild.default_role.id, channel.guild.me.id}
            or getattr(overwrite, name) is True
        }
        if fields:
            result[str(target.id)] = {
                "role": isinstance(target, discord.Role),
                "fields": fields,
                "allow": target.id == channel.guild.me.id,
            }
    return result


class LockdownService:
    def __init__(self, bot):
        self.bot = bot
        self.locks = WeakValueDictionary()

    def guild_lock(self, guild_id):
        lock = self.locks.get(guild_id)
        if lock is None:
            lock = asyncio.Lock()
            self.locks[guild_id] = lock
        return lock

    async def apply(self, channel, *, raid=False, unlock=False):
        """Caller holds guild lock. Save before Discord changes; retain failures for retry."""
        channel = await self.bot.fetch_channel(channel.id)
        async with self.bot.db_session() as session:
            record = await session.get(ChannelLock, channel.id)
            if record is None:
                if unlock:
                    return "No saved lock"
                record = ChannelLock(
                    channel_id=channel.id,
                    guild_id=channel.guild.id,
                    single=not raid,
                    raid=raid,
                    snapshot=snapshot_for(channel),
                )
                session.add(record)
            else:
                setattr(record, "raid" if raid else "single", not unlock)
            await session.commit()
            if unlock and (record.single or record.raid):
                return "Other lock still active"
            snapshot = record.snapshot
        conflicts = []
        # Always fetch current state so restore won't overwrite unrelated changes.
        channel = await self.bot.fetch_channel(channel.id)
        for target_id, saved in snapshot.items():
            target = (
                channel.guild.get_role(int(target_id))
                if saved["role"]
                else channel.guild.get_member(int(target_id))
            )
            if target is None:
                if saved["role"]:
                    continue
                try:
                    target = await channel.guild.fetch_member(int(target_id))
                except discord.NotFound:
                    continue
            overwrite = channel.overwrites_for(target)
            changed = False
            for name, original in saved["fields"].items():
                current = getattr(overwrite, name)
                if unlock:
                    if current == original:
                        continue
                    if current is not saved.get("allow", False):
                        conflicts.append(target_id)
                        continue
                    setattr(overwrite, name, original)
                else:
                    setattr(overwrite, name, saved.get("allow", False))
                changed = True
            if changed:
                await channel.set_permissions(
                    target,
                    overwrite=None if overwrite.is_empty() else overwrite,
                    reason="Meyaya unlock" if unlock else "Meyaya lockdown",
                )
        if unlock and not conflicts:
            async with self.bot.db_session() as session:
                record = await session.get(ChannelLock, channel.id)
                if record:
                    await session.delete(record)
                    await session.commit()
        return (
            "Manual permission changes kept; review and retry"
            if conflicts
            else ("Unlocked" if unlock else "Locked")
        )
