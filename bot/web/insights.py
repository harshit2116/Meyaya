"""Safe dashboard summaries from existing observations and server permissions."""
from collections import Counter
from datetime import UTC, datetime
import math
from bot.logging.health import health
from bot.logging.telemetry import operations


def overview(bot, servers):
    now = datetime.now(UTC)
    snapshot = operations.snapshot()
    failures = [e for e in health.errors.values() if e.get('timestamp', '')[:10] == now.date().isoformat()]
    issues = []
    by_guild = Counter(str(e.get('guild_id')) for e in failures)
    for server in servers:
        if server.get('membership') == 'removed':
            continue
        gid = server['id']
        guild = bot.get_guild(int(gid))
        missing = []
        if guild and guild.me:
            perms = guild.me.guild_permissions
            missing = [label for key, label in [('view_channel', 'View Channels'), ('send_messages', 'Send Messages'),
                        ('embed_links', 'Embed Links'), ('attach_files', 'Attach Files')]
                       if not getattr(perms, key, False)]
        if missing:
            issues.append(dict(guild_id=gid, kind='permissions', title='Missing server permissions',
                               detail=', '.join(missing), diagnostic='permissions'))
        if not server.get('exempt') and server.get('today_chats', 0) >= server.get('limit', 40):
            issues.append(dict(guild_id=gid, kind='quota', title='Chat allowance exhausted',
                               detail='Daily chat allowance resets at 00:00 UTC.', diagnostic='settings'))
        if by_guild[gid] >= 2:
            issues.append(dict(guild_id=gid, kind='failures', title='Repeated failures today',
                               detail=f'{by_guild[gid]} recorded errors; inspect their error IDs.', diagnostic='errors'))
        voice = [e for e in failures if str(e.get('guild_id')) == gid and
                 'voice' in (str(e.get('command', '')) + str(e.get('stage', ''))).lower()]
        if voice:
            issues.append(dict(guild_id=gid, kind='voice', title='Voice errors today',
                               detail=f'{len(voice)} recorded voice errors.', diagnostic='errors'))
    latency = getattr(bot, 'latency', None)
    return dict(generated_at=now.isoformat(), uptime_seconds=round(now.timestamp()-health.started_at),
        gateway_latency_ms=round(latency*1000, 1) if isinstance(latency, (int,float)) and math.isfinite(latency) else None,
        response_latency_ms=snapshot['summary']['average_latency_ms'],
        active_voice_sessions=len(getattr(getattr(bot, 'ai_guard', None), 'voice_guilds', ())),
        failed_requests_today=operations.failed_today(),
        observation_scope='Failures counted since process start or midnight UTC; latency uses the latest retained AI requests.',
        issues=issues)
