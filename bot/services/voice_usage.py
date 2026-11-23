"""Idempotent voice checkpoints and lightweight per-server totals."""
from datetime import UTC, datetime, timedelta
from sqlalchemy import select, func, case
from sqlalchemy.dialects.postgresql import insert
from bot.models.voice_usage import GuildVoiceUsage


EMPTY_VOICE_TOTALS = {
    'total_voice_seconds': 0,
    'today_voice_seconds': 0,
    'week_voice_seconds': 0,
    'today_voice_sessions': 0,
    'week_voice_sessions': 0,
}


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
    week_start = today - timedelta(days=6)
    snapshots = [s.voice_usage_snapshot() for s in active if hasattr(s, 'voice_usage_snapshot')]
    snapshots = [s for s in snapshots if s is not None]
    today_activity = (GuildVoiceUsage.day == today) & (GuildVoiceUsage.seconds > 0)
    week_activity = GuildVoiceUsage.day.between(week_start, today) & (GuildVoiceUsage.seconds > 0)
    statement = select(
        GuildVoiceUsage.guild_id,
        func.sum(GuildVoiceUsage.seconds).label('total_voice_seconds'),
        func.sum(case((GuildVoiceUsage.day == today, GuildVoiceUsage.seconds), else_=0)).label('today_voice_seconds'),
        func.sum(case((GuildVoiceUsage.day >= week_start, GuildVoiceUsage.seconds), else_=0)).label('week_voice_seconds'),
        func.count(GuildVoiceUsage.session_id.distinct()).filter(today_activity).label('today_voice_sessions'),
        func.count(GuildVoiceUsage.session_id.distinct()).filter(week_activity).label('week_voice_sessions'),
    ).group_by(GuildVoiceUsage.guild_id)
    if snapshots:
        statement = statement.where(GuildVoiceUsage.session_id.not_in([s['session_id'] for s in snapshots]))
    async with factory() as session:
        rows = (await session.execute(statement)).mappings().all()
    result = {row['guild_id']: dict(EMPTY_VOICE_TOTALS, **{
        key: value for key, value in row.items() if key != 'guild_id'
    }) for row in rows}
    for snapshot in snapshots:
        target = result.setdefault(snapshot['guild_id'], EMPTY_VOICE_TOTALS.copy())
        days = snapshot['days']
        target['today_voice_sessions'] += int(days.get(today, 0) > 0)
        target['week_voice_sessions'] += int(any(week_start <= day <= today and seconds > 0
                                                 for day, seconds in days.items()))
        for day, seconds in days.items():
            target['total_voice_seconds'] += seconds
            if day==today: target['today_voice_seconds'] += seconds
            if week_start<=day<=today: target['week_voice_seconds'] += seconds
    return result
