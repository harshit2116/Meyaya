"""Database-backed owner dashboard, with no Discord connection or AI client."""
import argparse
import asyncio
import os
import secrets
from pathlib import Path
from types import SimpleNamespace

from aiohttp import web
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


class LocalBackend:
    def __init__(self, settings):
        self.settings = settings
        self.engine = build_async_engine(settings.database_url)
        self.db_session = build_session_factory(self.engine)
        self.usage = UsageService(self.db_session, settings.quota_exempt_guild_id)
        self.request_log = RequestLogService(self.db_session)
        self.chat_blacklist = ChatBlacklistService(self.db_session)
        self.guilds_by_id = {}

    async def refresh(self):
        async with self.db_session() as session:
            ids = await session.scalars(union(*(select(model.guild_id) for model in (
                GuildSettings, GuildUsage, RequestLog, BotMemory, MeyayaUserState, ChatBlacklist
            ))))
            self.guilds_by_id = {gid: SimpleNamespace(id=gid, name=f"Server {gid}", get_member=lambda _: None)
                                 for gid in ids if gid is not None}

    def get_guild(self, guild_id):
        return self.guilds_by_id.get(guild_id)

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
            rows.append(dict(id=str(gid), name=guild.name, local=True,
                prefix=config.command_prefix if config else 'uwu',
                autoresponder=config.autoresponder_enabled if config else False,
                exempt=gid == self.bot.settings.quota_exempt_guild_id,
                limit=limits.get(gid, 40),
                **usage.get(gid, dict(today_chats=0, today_commands=0, week_chats=0, week_commands=0))))
        return web.json_response(dict(ready=True, mode='local', servers=rows))

    async def operations(self, request):
        raise web.HTTPServiceUnavailable(text='Live process telemetry is only available on the hosted bot; database reports remain available locally.')

    async def safety(self, request):
        return web.json_response(dict(mode='local'))


async def serve(port):
    # Ignore host deployment overrides: this launcher must never bind publicly.
    os.environ.pop('PORT', None)
    settings = Settings(DISCORD_TOKEN='', REDIS_URL='', DASHBOARD_HOST='127.0.0.1',
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
        await asyncio.Event().wait()
    finally:
        await dashboard.close()
        await backend.engine.dispose()


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Port must be between 1 and 65535')
    os.chdir(Path(__file__).resolve().parents[2])
    try:
        asyncio.run(serve(args.port))
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    except Exception as error:
        # Do not print connection strings from database exception messages.
        raise SystemExit(f'Dashboard could not start ({type(error).__name__}). Check DATABASE_URL and whether the port is free.') from None


if __name__ == '__main__':
    run()
