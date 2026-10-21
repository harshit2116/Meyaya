"""Idempotent voice checkpoints and lightweight per-server totals."""
from datetime import UTC, datetime, timedelta
from sqlalchemy import select, func, case
from sqlalchemy.dialects.postgresql import insert
from bot.models.voice_usage import GuildVoiceUsage


def daily_seconds(started_at, elapsed):
    start = started_at.astimezone(UTC)
    end = start + timedelta(seconds=max(0, elapsed))
    result = {}
    while start < end:
        midnight = datetime.combine(start.date()+timedelta(days=1), datetime.min.time(), tzinfo=UTC)
        stop = min(end, midnight)
        result[start.date()] = (stop-start).total_seconds()
        start = stop
    return result


async def checkpoint(factory, session_id, guild_id, days):
    if not days:
        return
    async with factory() as session:
        for day, seconds in days.items():
            statement = insert(GuildVoiceUsage).values(session_id=session_id, guild_id=guild_id, day=day, seconds=seconds)
            await session.execute(statement.on_conflict_do_update(
                index_elements=[GuildVoiceUsage.session_id, GuildVoiceUsage.day],
                set_={'seconds': func.greatest(GuildVoiceUsage.seconds, statement.excluded.seconds)}))
        await session.commit()


async def report(factory, active=()):
    today = datetime.now(UTC).date()
    snapshots = [s.voice_usage_snapshot() for s in active if hasattr(s, 'voice_usage_snapshot')]
    snapshots = [s for s in snapshots if s is not None]
    statement = select(GuildVoiceUsage.guild_id,
        func.sum(GuildVoiceUsage.seconds).label('total_voice_seconds'),
        func.sum(case((GuildVoiceUsage.day==today, GuildVoiceUsage.seconds),else_=0)).label('today_voice_seconds'),
        func.sum(case((GuildVoiceUsage.day>=today-timedelta(days=6), GuildVoiceUsage.seconds),else_=0)).label('week_voice_seconds')).group_by(GuildVoiceUsage.guild_id)
    if snapshots:
        statement = statement.where(GuildVoiceUsage.session_id.not_in([s['session_id'] for s in snapshots]))
    async with factory() as session:
        rows = (await session.execute(statement)).mappings().all()
    result = {row['guild_id']: {k: float(v or 0) for k,v in row.items() if k!='guild_id'} for row in rows}
    for snapshot in snapshots:
        target = result.setdefault(snapshot['guild_id'], dict(total_voice_seconds=0,today_voice_seconds=0,week_voice_seconds=0))
        for day, seconds in snapshot['days'].items():
            target['total_voice_seconds'] += seconds
            if day==today: target['today_voice_seconds'] += seconds
            if today-timedelta(days=6)<=day<=today: target['week_voice_seconds'] += seconds
    return result
