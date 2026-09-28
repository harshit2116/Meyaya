"""Capture explicit AI requests and delivered replies, never prompts or ambient chat."""

import asyncio
import json
import logging
import time
from datetime import UTC, datetime, timedelta
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from bot.models.request_log import RequestLog

logger = logging.getLogger(__name__)
RETENTION_DAYS = 7
MAX_CONTENT = 8000


def slash_content(data: dict) -> str:
    """Keep explicit option values only, not resolved users, attachments or credentials."""

    def options(items):
        result = []
        for item in items:
            name = str(item.get("name", ""))
            if "options" in item:
                result.append(name + " " + options(item["options"]))
            elif "value" in item:
                result.append(name + ":" + json.dumps(item["value"], ensure_ascii=False))
            else:
                result.append(name)
        return " ".join(result)

    return ("/" + str(data.get("name", "command")) + " " + options(data.get("options", []))).strip()


class RequestLogService:
    def __init__(self, sessions):
        self.sessions = sessions
        self._last_failure = float("-inf")
        self._pending = set()
        self._closing = False
        # Review logging must not occupy the whole three-connection DB pool.
        self._write_slot = asyncio.Semaphore(1)

    async def record(
        self, *, event_id, guild_id, channel_id, user_id, user_name, kind, content, message_id=None,
        response=None
    ):
        if guild_id is None or channel_id is None:
            return
        bounded = (
            content
            if len(content) <= MAX_CONTENT
            else content[: MAX_CONTENT - 20] + "\n[content truncated]"
        )
        started = time.monotonic()
        visible_response = (response if response is None or len(response) <= MAX_CONTENT
                            else response[:MAX_CONTENT - 20] + '\n[content truncated]')
        try:
            async with asyncio.timeout(3):
                async with self.sessions() as session:
                    statement = (insert(RequestLog)
                        .values(
                            event_id=event_id,
                            guild_id=guild_id,
                            channel_id=channel_id,
                            user_id=user_id,
                            user_name=user_name[:200],
                            kind=kind,
                            content=bounded,
                            message_id=message_id,
                            response=visible_response,
                        ))
                    statement = (statement.on_conflict_do_nothing(index_elements=[RequestLog.event_id])
                                 if response is None else statement.on_conflict_do_update(
                                     index_elements=[RequestLog.event_id],
                                     set_={'response': statement.excluded.response}))
                    await session.execute(statement)
                    await session.commit()
        except (SQLAlchemyError, TimeoutError):
            now = time.monotonic()
            if now - self._last_failure >= 60:
                logger.warning(
                    "Request review logging unavailable; some requests were not recorded"
                )
                self._last_failure = now
        finally:
            elapsed = (time.monotonic() - started) * 1000
            if elapsed >= 500:
                logger.info("request_log write_ms=%.0f", elapsed)

    async def record_message(self, message, kind="chat", *, response=None):
        if message.guild is None or message.author.bot:
            return
        if self._closing or kind != "chat":
            return
        if len(self._pending) >= 8:
            now = time.monotonic()
            if now - self._last_failure >= 60:
                logger.warning("Request review logging busy; skipping new entry")
                self._last_failure = now
            return
        # Only retain bounded scalar fields, never the entire Discord message.
        task = asyncio.create_task(self._queued_record(
            event_id=message.id,
            guild_id=message.guild.id,
            channel_id=message.channel.id,
            user_id=message.author.id,
            user_name=str(message.author),
            kind=kind,
            content=(message.content or "[No text supplied]")[:MAX_CONTENT],
            message_id=message.id,
            response=response[:MAX_CONTENT] if response is not None else None,
        ), name="chat-request-log")
        self._pending.add(task)
        task.add_done_callback(self._record_done)

    async def _queued_record(self, **fields):
        async with self._write_slot:
            await self.record(**fields)

    def _record_done(self, task):
        self._pending.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.warning("Request review logging failed")

    async def close(self):
        self._closing = True
        if self._pending:
            _, pending = await asyncio.wait(tuple(self._pending), timeout=3)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    async def page(self, guild_id: int, before: int | None = None):
        cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)
        statement = select(RequestLog).where(
            RequestLog.guild_id == guild_id, RequestLog.created_at >= cutoff,
            RequestLog.kind == 'chat',
        )
        if before is not None:
            statement = statement.where(RequestLog.event_id < before)
        async with self.sessions() as session:
            rows = (
                (await session.execute(statement.order_by(RequestLog.event_id.desc()).limit(51)))
                .scalars()
                .all()
            )
        items = [
            {
                "id": str(row.event_id),
                "user_id": str(row.user_id),
                "user_name": row.user_name,
                "channel_id": str(row.channel_id),
                "kind": row.kind,
                "content": row.content,
                "response": row.response,
                "created_at": row.created_at.isoformat(),
                "url": f"https://discord.com/channels/{row.guild_id}/{row.channel_id}"
                + (f"/{row.message_id}" if row.message_id else ""),
            }
            for row in rows[:50]
        ]
        return {
            "items": items,
            "next_cursor": str(rows[49].event_id) if len(rows) > 50 else None,
            "retention_days": RETENTION_DAYS,
        }

    async def cleanup(self):
        async with self.sessions() as session:
            await session.execute(
                delete(RequestLog).where(
                    RequestLog.created_at < datetime.now(UTC) - timedelta(days=RETENTION_DAYS)
                )
            )
            await session.commit()

    async def maintenance(self):
        while True:
            try:
                async with asyncio.timeout(30):
                    await self.cleanup()
            except (SQLAlchemyError, TimeoutError):
                logger.warning("Request log retention cleanup unavailable; will retry in one hour")
            await asyncio.sleep(3600)
