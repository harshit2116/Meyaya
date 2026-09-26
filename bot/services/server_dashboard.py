"""Small, guild-scoped queries for the in-Discord server dashboard."""

from datetime import UTC, datetime, timedelta

import discord
from sqlalchemy import func, select

from bot.models.guild_settings import GuildSettings
from bot.models.moderation import ModerationSettings
from bot.models.request_log import RequestLog
from bot.models.usage import GuildUsage
from bot.utils.embeds import meyaya_embed


async def server_overview(bot, guild_id):
    now = datetime.now(UTC)
    today = now.date()
    async with bot.db_session() as session:
        settings = await session.get(GuildSettings, guild_id)
        usage = await session.get(GuildUsage, (guild_id, today))
        moderation = await session.get(ModerationSettings, guild_id)
        count = func.count(RequestLog.event_id)
        # Request logs are retained for 7 days. These are submitted chat requests,
        # not guaranteed successful replies, and never include ambient messages.
        top = (await session.execute(
            select(RequestLog.user_id, count.label("requests"))
            .where(RequestLog.guild_id == guild_id, RequestLog.kind == "chat",
                   RequestLog.created_at >= now - timedelta(days=7))
            .group_by(RequestLog.user_id)
            .order_by(count.desc(), RequestLog.user_id).limit(3)
        )).all()
        limit = settings.daily_chat_limit if settings else 40
        used = usage.chats if usage else 0
        unlimited = guild_id == bot.settings.quota_exempt_guild_id
        return {
            "limit": limit, "used": used, "unlimited": unlimited,
            "remaining": None if unlimited else max(0, limit - used),
            "commands": usage.commands if usage else 0,
            "reset": int(datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=UTC).timestamp()),
            "channel": settings.chat_channel_id if settings else None,
            "autoresponder": settings.autoresponder_enabled if settings else False,
            "prefix": settings.command_prefix if settings else "uwu",
            "moderation": {name: getattr(moderation, name) if moderation else name != "raid_active"
                           for name in ("probation", "cross_spam", "anti_invite", "raid_active")},
            "top": [(row[0], row[1]) for row in top],
        }


def dashboard_embed(guild, data):
    embed = meyaya_embed("Server Dashboard", discord.utils.escape_markdown(guild.name), icon="📊")
    allowance = "Unlimited" if data["unlimited"] else str(data["limit"])
    remaining = "Unlimited" if data["unlimited"] else str(data["remaining"])
    embed.add_field(name="Today's messages", value=f"Allowance **{allowance}**\nUsed **{data['used']}**\nRemaining **{remaining}**", inline=True)
    embed.add_field(name="Today's activity", value=f"Commands completed **{data['commands']}**\nResets <t:{data['reset']}:R>\nMidnight UTC", inline=True)
    embed.add_field(name="Most chat requests - last 7 days", value=(
        "\n".join(f"{index}. <@{member_id}> - {count} requests" for index, (member_id, count) in enumerate(data["top"], 1))
        or "No chat requests recorded yet."
    ) + "\nCounts submitted mentions/replies, including requests that may not have received a response.", inline=False)
    channel = f"<#{data['channel']}>" if data["channel"] else "Entire server"
    embed.add_field(name="Chat settings", value=f"Access: {channel}\nAutomatic replies: {'On' if data['autoresponder'] else 'Off'}\nPrefix: `{data['prefix']}`", inline=False)
    labels = {"probation": "3-day probation", "cross_spam": "Cross-channel spam protection", "anti_invite": "Other-server invite blocking", "raid_active": "Raid lockdown"}
    embed.add_field(name="Moderation", value="\n".join(f"{label}: {'On' if data['moderation'][key] else 'Off'}" for key, label in labels.items()), inline=False)
    return embed
