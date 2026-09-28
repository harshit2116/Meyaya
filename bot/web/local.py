"""Database-backed owner dashboard, with no Discord connection or AI client."""
import argparse
import asyncio
import os
import secrets
import time
import webbrowser
from pathlib import Path
from types import SimpleNamespace

from aiohttp import ClientSession, ClientTimeout, ClientError, web
from sqlalchemy import select, union
from bot.config.settings import Settings
from bot.database.session import build_async_engine, build_session_factory
from bot.models.guild_settings import GuildSettings
from bot.models.usage import GuildUsage
from bot.models.request_log import RequestLog
from bot.models.memory import BotMemory
from bot.models.meyaya_state import MeyayaUserState
from bot.models.chat_blacklist import ChatBlacklist
from bot.services.usage import UsageService
from bot.services.request_log import RequestLogService
from bot.services.chat_blacklist import ChatBlacklistService
from bot.web.dashboard import Dashboard
from bot.web.server_info import rest_server_info, rest_member_preview


class LocalBackend:
    def __init__(self, settings):
        self.settings = settings
        self.engine = build_async_engine(settings.database_url)
        self.db_session = build_session_factory(self.engine)
        self.usage = UsageService(self.db_session, settings.quota_exempt_guild_id)
        self.request_log = RequestLogService(self.db_session)
        self.chat_blacklist = ChatBlacklistService(self.db_session)
        self.guilds_by_id = {}
        self._guild_names = {}
        self._names_refresh_at = 0
        self._names_lock = asyncio.Lock()
        self._guild_metadata = {}
        self._details_cache = {}
        self._summary_cache = {}
        self._details_lock = asyncio.Lock()
        self._summary_lock = asyncio.Lock()
        self._discord_retry_at = 0

    async def refresh_names(self):
        """Read names over REST, never start another Discord gateway session."""
        async with self._names_lock:
            if time.monotonic() < self._names_refresh_at:
                return
            self._names_refresh_at = time.monotonic() + 300
            if not self.settings.discord_token:
                return
            names = {}
            after = None
            try:
                async with asyncio.timeout(20), ClientSession(
                    timeout=ClientTimeout(total=10),
                    headers={'Authorization': f'Bot {self.settings.discord_token}'},
                ) as client:
                    while True:
                        params = {'limit': '200', 'with_counts': 'true'}
                        if after:
                            params['after'] = after
                        async with client.get('https://discord.com/api/v10/users/@me/guilds', params=params) as response:
                            if response.status == 429:
                                retry = (await response.json()).get('retry_after', 300)
                                self._names_refresh_at = time.monotonic() + max(300, float(retry))
                                return
                            if response.status != 200:
                                return  # Retain cached names during outages or token errors.
                            rows = await response.json()
                        names.update({int(row['id']): row['name'] for row in rows})
                        self._guild_metadata = getattr(self, '_guild_metadata', {})
                        self._guild_metadata.update({int(row['id']): row for row in rows})
                        if len(rows) < 200:
                            break
                        cursor = str(rows[-1]['id'])
                        if cursor == after:
                            return
                        after = cursor
                self._guild_names = names
                self._guild_metadata = {gid: self._guild_metadata[gid] for gid in names}
            except (ClientError, TimeoutError, ValueError, KeyError, TypeError):
                pass  # Never log credentials or provider response bodies.

    async def refresh(self):
        await self.refresh_names()
        async with self.db_session() as session:
            ids = await session.scalars(union(*(select(model.guild_id) for model in (
                GuildSettings, GuildUsage, RequestLog, BotMemory, MeyayaUserState, ChatBlacklist
            ))))
            # New/quiet servers may not have any database rows yet.
            all_ids = {gid for gid in ids if gid is not None} | self._guild_names.keys()
            self.guilds_by_id = {gid: SimpleNamespace(id=gid, name=self._guild_names.get(gid, f"Server {gid}"), get_member=lambda _: None)
                                 for gid in all_ids}

    def get_guild(self, guild_id):
        return self.guilds_by_id.get(guild_id)

    async def server_details(self, guild_id, *, summary=False):
        """Bounded on-demand reads including one 50-member page; no gateway."""
        if summary and not hasattr(self, '_summary_lock'):
            self._summary_lock = asyncio.Lock()
        async with self._summary_lock if summary else self._details_lock:
            if not hasattr(self, '_summary_cache'):
                self._summary_cache = {}
            cache = self._summary_cache if summary else self._details_cache
            cached = cache.get(guild_id)
            if summary:
                full = self._details_cache.get(guild_id)
                if full and time.monotonic() < full[0]:
                    cached = full
            now = time.monotonic()
            if cached and now < cached[0]:
                return cached[1]
            if now < self._discord_retry_at:
                if cached:
                    return dict(cached[1], stale=True)
                raise web.HTTPServiceUnavailable(text='Discord is rate limited; retry shortly.')
            if not self.settings.discord_token:
                raise web.HTTPServiceUnavailable(text='Discord bot token is not configured.')
            try:
                async with asyncio.timeout(20), ClientSession(
                    timeout=ClientTimeout(total=8),
                    headers={'Authorization': f'Bot {self.settings.discord_token}'},
                ) as client:
                    async def get(path, *, required=False, params=None):
                        async with client.get(f'https://discord.com/api/v10/{path}', params=params) as response:
                            if response.status == 429:
                                body = await response.json()
                                self._discord_retry_at = time.monotonic() + max(1, float(body.get('retry_after', 60)))
                                raise web.HTTPServiceUnavailable(text='Discord is rate limited; retry shortly.')
                            if response.status != 200:
                                if required:
                                    raise web.HTTPServiceUnavailable(text='Discord server metadata unavailable. Check bot access.')
                                return None
                            return await response.json()
                    data = await get(f'guilds/{guild_id}', required=True, params={'with_counts': 'true'})
                    channels = None if summary else await get(f'guilds/{guild_id}/channels')
                    owner = await get(f'users/{data["owner_id"]}') if data.get('owner_id') else None
                    members = None if summary else await get(f'guilds/{guild_id}/members', params={'limit': '200'})
                details = rest_server_info(data, channels, owner)
                details['member_preview'] = rest_member_preview(members, data.get('roles')) if members is not None else None
                if members is None and not summary:
                    details['member_preview_error'] = 'Member list unavailable. Check bot access and Server Members Intent.'
                details.update(source='Discord REST (5-minute cache)', fetched_at=time.time(),
                               partial=owner is None or (not summary and (channels is None or members is None)))
                for gid in list(cache):
                    if gid not in self.guilds_by_id:
                        cache.pop(gid, None)
                cache[guild_id] = (time.monotonic() + 300, details)
                return details
            except (ClientError, TimeoutError, ValueError, KeyError, TypeError, web.HTTPServiceUnavailable):
                self._discord_retry_at = max(self._discord_retry_at, time.monotonic() + 15)
                if cached:
                    cache[guild_id] = (time.monotonic() + 30, dict(cached[1], stale=True))
                    return dict(cached[1], stale=True)
                raise web.HTTPServiceUnavailable(text='Discord metadata temporarily unavailable; retry shortly.') from None

    def cache_guild_prefix(self, *args):
        pass  # The hosted process reloads committed settings periodically.

    def cache_autoresponder(self, *args):
        pass


class LocalDashboard(Dashboard):
    def __init__(self, backend):
        super().__init__(backend, local_no_auth=True)
        @web.middleware
        async def refresh_catalog(request, handler):
            # This middleware runs after authentication; no public database query.
            if request.path.startswith('/api/') and request.path not in {'/api/login', '/api/logout'}:
                await backend.refresh()
            return await handler(request)
        self.app.middlewares.append(refresh_catalog)

    async def index(self, request):
        response = await super().index(request)
        response.text = response.text.replace('<body>', '<body data-local-dashboard="true">')
        return response

    async def servers(self, request):
        usage, limits = await self.bot.usage.report()
        async with self.bot.db_session() as session:
            records = (await session.scalars(select(GuildSettings))).all()
        settings = {row.guild_id: row for row in records}
        rows = []
        for gid, guild in sorted(self.bot.guilds_by_id.items()):
            config = settings.get(gid)
            metadata = self.bot._guild_metadata.get(gid, {})
            details = self.bot._details_cache.get(gid, (0, {}))[1]
            summary = self.bot._summary_cache.get(gid, (0, {}))[1]
            rows.append(dict(id=str(gid), name=guild.name, local=True,
                members=metadata.get('approximate_member_count'), members_approximate=True,
                owner_id=details.get('owner_id') or summary.get('owner_id'),
                owner_name=details.get('owner_name') or summary.get('owner_name'),
                icon_url=rest_server_info(dict(metadata, id=str(gid))).get('icon_url'),
                prefix=config.command_prefix if config else 'uwu',
                autoresponder=config.autoresponder_enabled if config else False,
                exempt=gid == self.bot.settings.quota_exempt_guild_id,
                limit=limits.get(gid, 40),
                **usage.get(gid, dict(today_chats=0, today_commands=0, week_chats=0, week_commands=0))))
        return web.json_response(dict(ready=True, mode='local', servers=rows))

    async def server_details(self, request):
        try:
            guild_id = int(request.match_info['guild_id'])
            if not 0 < guild_id < 2**64:
                raise ValueError()
        except ValueError:
            raise web.HTTPBadRequest(text='Invalid server ID')
        if guild_id not in self.bot._guild_names:
            raise web.HTTPNotFound(text='Bot is not currently in this server')
        return web.json_response(await self.bot.server_details(guild_id))

    async def operations(self, request):
        raise web.HTTPServiceUnavailable(text='Live process telemetry is only available on the hosted bot; database reports remain available locally.')

    async def server_summary(self, request):
        try:
            guild_id = int(request.match_info['guild_id'])
            if not 0 < guild_id < 2**64:
                raise ValueError()
        except ValueError:
            raise web.HTTPBadRequest(text='Invalid server ID')
        if guild_id not in self.bot._guild_names:
            raise web.HTTPNotFound(text='Bot is not currently in this server')
        details = await self.bot.server_details(guild_id, summary=True)
        return web.json_response({key: details.get(key) for key in ('id', 'name', 'owner_id', 'owner_name', 'icon_url')})

    async def safety(self, request):
        return web.json_response(dict(mode='local'))


async def serve(port, *, open_browser=False):
    # Ignore host deployment overrides: this launcher must never bind publicly.
    os.environ.pop('PORT', None)
    settings = Settings(REDIS_URL='', DASHBOARD_HOST='127.0.0.1',
        DASHBOARD_PORT=port, DASHBOARD_PUBLIC_URL='', DASHBOARD_TRUSTED_PROXIES='',
        DASHBOARD_TOKEN=secrets.token_urlsafe(48))
    backend = LocalBackend(settings)
    dashboard = LocalDashboard(backend)
    try:
        await backend.refresh()
        await dashboard.start()
        print('Local dashboard only. No Discord login, migrations, or AI requests.', flush=True)
        print(f'Open http://127.0.0.1:{port} - no login required on this laptop.', flush=True)
        print('Anyone using this laptop can access it while running. Ctrl+C to stop.', flush=True)
        if open_browser:
            # Open only after a successful bind, never on a fixed startup timer.
            try:
                await asyncio.to_thread(webbrowser.open, f'http://127.0.0.1:{port}')
            except webbrowser.Error:
                print('Could not open the browser automatically. Use the URL above.', flush=True)
        await asyncio.Event().wait()
    finally:
        await dashboard.close()
        await backend.engine.dispose()


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--open-browser', action='store_true', help='Open your browser once the dashboard is ready')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Port must be between 1 and 65535')
    os.chdir(Path(__file__).resolve().parents[2])
    try:
        asyncio.run(serve(args.port, open_browser=args.open_browser))
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    except Exception as error:
        # Do not print connection strings from database exception messages.
        raise SystemExit(f'Dashboard could not start ({type(error).__name__}). Check DATABASE_URL and whether the port is free.') from None


if __name__ == '__main__':
    run()
