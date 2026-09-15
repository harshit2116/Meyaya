"""Atomic daily allowances shared by chat, roleplay and automatic replies."""

from datetime import UTC, datetime, timedelta
import re
from sqlalchemy import select, update, func
from sqlalchemy.dialects.postgresql import insert
from bot.models.usage import GuildUsage
from bot.models.guild_settings import GuildSettings


class ChatLimitReached(Exception):
    pass


def is_silence(text: str) -> bool:
    return re.sub(r"[^a-z_]", "", text.casefold()) == "no_reply"


class UsageService:
    def __init__(self, session_factory, exempt_guild_id):
        self.sessions = session_factory
        self.exempt_guild_id = exempt_guild_id

    async def reserve(self, guild_id):
        day = datetime.now(UTC).date()
        async with self.sessions() as session:
            limit = await session.scalar(
                select(GuildSettings.daily_chat_limit).where(GuildSettings.guild_id == guild_id)
            )
            limit = 40 if limit is None else limit
            unlimited = guild_id == self.exempt_guild_id
            if limit == 0 and not unlimited:
                raise ChatLimitReached("AI chat is disabled in this server.")
            statement = insert(GuildUsage).values(guild_id=guild_id, day=day, chats=1)
            statement = statement.on_conflict_do_update(
                index_elements=[GuildUsage.guild_id, GuildUsage.day],
                set_={"chats": GuildUsage.chats + 1},
                where=True if unlimited else GuildUsage.chats < limit,
            ).returning(GuildUsage.chats)
            count = await session.scalar(statement)
            if count is None:
                raise ChatLimitReached(
                    f"This server has used its {limit} daily AI messages. The allowance resets at midnight UTC."
                )
            await session.commit()
        return day

    async def refund(self, guild_id, day):
        async with self.sessions() as session:
            await session.execute(
                update(GuildUsage)
                .where(GuildUsage.guild_id == guild_id, GuildUsage.day == day)
                .values(chats=func.greatest(0, GuildUsage.chats - 1))
            )
            await session.commit()

    async def command_completed(self, guild_id):
        async with self.sessions() as session:
            statement = insert(GuildUsage).values(
                guild_id=guild_id, day=datetime.now(UTC).date(), commands=1
            )
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=[GuildUsage.guild_id, GuildUsage.day],
                    set_={"commands": GuildUsage.commands + 1},
                )
            )
            await session.commit()

    async def report(self):
        today = datetime.now(UTC).date()
        async with self.sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(GuildUsage).where(GuildUsage.day >= today - timedelta(days=6))
                    )
                )
                .scalars()
                .all()
            )
            settings = (await session.execute(select(GuildSettings))).scalars().all()
        result = {}
        for row in rows:
            item = result.setdefault(
                row.guild_id,
                {"today_chats": 0, "today_commands": 0, "week_chats": 0, "week_commands": 0},
            )
            item["week_chats"] += row.chats
            item["week_commands"] += row.commands
            if row.day == today:
                item["today_chats"] = row.chats
                item["today_commands"] = row.commands
        return result, {row.guild_id: row.daily_chat_limit for row in settings}
