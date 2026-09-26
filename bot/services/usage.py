"""Atomic daily allowances shared by chat, roleplay and automatic replies."""

from datetime import UTC, datetime, timedelta
import re
from sqlalchemy import select, update, func, case
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
                raise ChatLimitReached("Meyaya chat is disabled in this server.")
            statement = insert(GuildUsage).values(guild_id=guild_id, day=day, chats=1)
            statement = statement.on_conflict_do_update(
                index_elements=[GuildUsage.guild_id, GuildUsage.day],
                set_={"chats": GuildUsage.chats + 1},
                where=True if unlimited else GuildUsage.chats < limit,
            ).returning(GuildUsage.chats)
            count = await session.scalar(statement)
            if count is None:
                raise ChatLimitReached(
                    f"This server has used its {limit} daily Meyaya messages. The allowance resets at midnight UTC."
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
                        select(
                            GuildUsage.guild_id,
                            func.sum(
                                case((GuildUsage.day == today, GuildUsage.chats), else_=0)
                            ).label("today_chats"),
                            func.sum(
                                case((GuildUsage.day == today, GuildUsage.commands), else_=0)
                            ).label("today_commands"),
                            func.sum(GuildUsage.chats).label("week_chats"),
                            func.sum(GuildUsage.commands).label("week_commands"),
                        )
                        .where(GuildUsage.day >= today - timedelta(days=6))
                        .group_by(GuildUsage.guild_id)
                    )
                )
                .mappings()
                .all()
            )
            settings = (
                await session.execute(
                    select(GuildSettings.guild_id, GuildSettings.daily_chat_limit)
                )
            ).all()
        result = {
            row["guild_id"]: {key: value for key, value in row.items() if key != "guild_id"}
            for row in rows
        }
        return result, {row.guild_id: row.daily_chat_limit for row in settings}
