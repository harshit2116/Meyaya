"""Local-first owner dashboard using the existing aiohttp dependency."""

import hmac
import asyncio
import discord
import logging
import os
import secrets
import time
from urllib.parse import urlsplit
from pathlib import Path
from aiohttp import web
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from bot.logging.telemetry import operations as operational_telemetry
from bot.models.guild_settings import GuildSettings
from bot.services.guild_identity import saved_identities
from bot.models.memory import BotMemory, MemoryStatus
from bot.models.meyaya_state import MeyayaUserState
from bot.web.cache import AsyncTTLCache
from bot.web.security import DashboardSecurity, SESSION_SECONDS
from bot.web.server_info import cached_server_info, cached_member_preview
from bot.services.owner_health import OwnerHealth
from bot.logging.health import health as health_telemetry, find_retained_error
import re
from datetime import UTC, datetime, timedelta
from bot.models.guild_identity import GuildEvent
from bot.services.guild_features import FEATURES, feature_states

logger = logging.getLogger(__name__)


async def server_report(bot, usage_report=None):
    usage, limits = usage_report if usage_report is not None else await bot.usage.report()
    monitor = bot.get_cog("MonitorCog")
    games = bot.get_cog("SocialGamesCog")
    voice = bot.get_cog("VoiceLiveCog")
    rows = []
    telemetry = operational_telemetry.guild_summaries(guild.id for guild in bot.guilds)
    for guild in sorted(bot.guilds, key=lambda item: item.name.casefold()):
        permissions = guild.me.guild_permissions if guild.me else None
        accessible = sum(
            1
            for channel in guild.text_channels
            if guild.me and channel.permissions_for(guild.me).view_channel
        )
        rows.append(
            {
                "id": str(guild.id),
                "name": guild.name,
                "members": guild.member_count,
                "owner_id": str(guild.owner_id),
                "owner_name": guild.owner.display_name if guild.owner else None,
                "icon_url": str(guild.icon.url) if guild.icon else None,
                "available": not guild.unavailable,
                "readable_channels": accessible,
                "can_timeout": bool(permissions and permissions.moderate_members),
                "prefix": bot.prefix_for_guild(guild.id),
                "autoresponder": bot.autoresponder_enabled(guild.id),
                "features": feature_states(getattr(bot, '_guild_disabled_features', {}).get(guild.id, ())),
                "exempt": guild.id == bot.settings.quota_exempt_guild_id,
                "limit": limits.get(guild.id, 40),
                "monitored_channels": monitor.monitored_channel_count(guild) if monitor else 0,
                "active_games": games.sessions.active_count(guild.id) if games else 0,
                "voice_active": bool(voice and voice.active_session(guild.id)),
                **telemetry[guild.id],
                **usage.get(
                    guild.id,
                    {"today_chats": 0, "today_commands": 0, "week_chats": 0, "week_commands": 0},
                ),
            }
        )
    return rows


class Dashboard:
    def __init__(self, bot, *, local_no_auth=False):
        self.bot = bot
        self._data_cache = AsyncTTLCache()
        self.owner_health = OwnerHealth(bot)
        self._error_search_lock = asyncio.Lock()
        self._error_search_cache = {}
        if local_no_auth and (bot.settings.dashboard_host != "127.0.0.1" or bot.settings.dashboard_public_url):
            raise ValueError("Token-free mode is restricted to the local dashboard")
        self.runner = None
        self._login_links = {}
        self._owner_names = {}
        self._owner_lock = asyncio.Lock()
        self._member_previews = {}
        self._member_lock = asyncio.Lock()
        self._member_names = {}
        self._member_name_slots = asyncio.Semaphore(3)
        self.security = DashboardSecurity(bot.settings)
        token = bot.settings.dashboard_token
        api_token = getattr(bot.settings, 'dashboard_api_token', '')
        edit_token = getattr(bot.settings, 'dashboard_edit_token', '')
        if edit_token and (len(edit_token) < 32 or edit_token == api_token):
            raise ValueError('DASHBOARD_EDIT_TOKEN must be distinct and at least 32 characters')
        if api_token and len(api_token) < 32:
            raise ValueError('DASHBOARD_API_TOKEN must contain at least 32 random characters')
        if len(token) < 32:
            raise ValueError("DASHBOARD_TOKEN must contain at least 32 random characters")

        @web.middleware
        async def security(request, handler):
            try:
                self.security.check_request(request)
                if request.path.startswith("/api/"):
                    if request.path == "/api/login":
                        self.security.throttle(request.remote)
                    elif not local_no_auth:
                        supplied = request.headers.get("Authorization", "")
                        api_access = bool(api_token and supplied.startswith('Bearer ') and hmac.compare_digest(supplied[7:].encode(), api_token.encode()))
                        edit_access = bool(edit_token and supplied.startswith('Bearer ') and hmac.compare_digest(supplied[7:].encode(), edit_token.encode()))
                        settings_edit = request.method == 'PATCH' and re.fullmatch(r'/api/servers/[0-9]+', request.path)
                        quota_reset = request.method == 'POST' and re.fullmatch(r'/api/servers/[0-9]+/reset-usage', request.path)
                        if edit_access and request.method not in {'GET', 'HEAD'} and not (settings_edit or quota_reset):
                            raise web.HTTPForbidden(text='Edit token is scoped to server settings')
                        request['dashboard_actor'] = 'dashboard edit token' if edit_access else 'owner session'
                        if api_access and request.method not in {'GET', 'HEAD'}:
                            raise web.HTTPForbidden(text='This API token is read-only')
                        if not api_access and not edit_access and (not supplied.startswith("Bearer ") or not self.security.authenticated(supplied[7:])):
                            self.security.throttle(request.remote)
                            raise web.HTTPUnauthorized(text="Owner session expired or missing")
                    if request.method not in {"GET", "HEAD"} and request.content_type != "application/json":
                        raise web.HTTPUnsupportedMediaType()
                response = await handler(request)
            except web.HTTPException as error:
                response = web.Response(status=error.status, headers=error.headers, body=error.body)
            except SQLAlchemyError as error:
                error_id = health_telemetry.capture(error, command='dashboard', stage='database')
                logger.warning("Dashboard database operation unavailable")
                response = web.json_response(
                    {"error": f"Database unavailable; please retry. Error ID: {error_id}"}, status=503
                )
            except Exception as error:
                # Never echo request bodies, credentials, or database errors.
                logger.error("Dashboard request failed (%s)", type(error).__name__)
                error_id = health_telemetry.capture(error, command='dashboard', stage='request')
                response = web.json_response({"error": f"Request unavailable; please retry. Error ID: {error_id}"}, status=500)
            response.headers.update(
                {
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                    "X-Frame-Options": "DENY",
                    "Referrer-Policy": "no-referrer",
                    "Content-Security-Policy": "default-src 'self'; img-src 'self' https://cdn.discordapp.com; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'; form-action 'self'",
                    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
                }
            )
            if getattr(self.bot.settings, "dashboard_public_url", "").startswith("https://"):
                response.headers["Strict-Transport-Security"] = "max-age=31536000"
            return response

        self.app = web.Application(middlewares=[security], client_max_size=4096)
        self.app.router.add_get("/", self.index)
        self.app.router.add_post("/api/login", self.login)
        self.app.router.add_post("/api/logout", self.logout)
        self.app.router.add_post("/api/window", self.window_login)
        self.app.router.add_get("/api/blacklist", self.blacklist)
        self.app.router.add_patch("/api/blacklist", self.update_blacklist)
        self.app.router.add_get("/dashboard.js", self.script)
        self.app.router.add_get("/dashboard.css", self.style)
        self.app.router.add_get('/meyaya-avatar.jpg', self.avatar)
        self.app.router.add_get("/api/servers", self.servers)
        self.app.router.add_get('/api/overview', self.overview)
        self.app.router.add_get('/api/servers/{guild_id}/insights', self.server_insights)
        self.app.router.add_get("/api/servers/{guild_id}/details", self.server_details)
        self.app.router.add_get("/api/servers/{guild_id}/summary", self.server_summary)
        self.app.router.add_get("/api/servers/{guild_id}/commands", self.server_commands)
        self.app.router.add_get("/api/servers/{guild_id}/requests", self.requests)
        self.app.router.add_get("/api/servers/{guild_id}/command-history", self.command_history)
        self.app.router.add_get("/api/memories", self.memories)
        self.app.router.add_get("/api/nicknames", self.nicknames)
        self.app.router.add_get("/api/operations", self.operations)
        self.app.router.add_get("/api/health", self.health)
        self.app.router.add_get("/api/errors", self.errors)
        self.app.router.add_get("/api/safety", self.safety)
        self.app.router.add_patch("/api/servers/{guild_id}", self.update)
        self.app.router.add_post("/api/servers/{guild_id}/reset-usage", self.reset_usage)

    def login_link(self):
        settings = self.bot.settings
        self.security.validate_config()
        base = (
            settings.dashboard_public_url
            or f"http://127.0.0.1:{os.environ.get('PORT', settings.dashboard_port)}"
        )
        parsed = urlsplit(base)
        if (
            parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("DASHBOARD_PUBLIC_URL must be a plain dashboard origin")
        if parsed.scheme != "https" and not (
            parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        ):
            raise ValueError("Remote dashboard links require HTTPS")
        now = time.monotonic()
        self._login_links = {
            key: expiry for key, expiry in self._login_links.items() if expiry > now
        }
        if len(self._login_links) >= 5:
            self._login_links.clear()
        code = secrets.token_urlsafe(32)
        self._login_links[code] = now + 60
        return base.rstrip("/") + "/#login=" + code

    async def login(self, request):
        if request.content_type != "application/json":
            raise web.HTTPUnsupportedMediaType()
        try:
            body = await request.json()
            code = body.get("code", "")
            supplied_token = body.get("token", "")
            if (not isinstance(code, str) or not isinstance(supplied_token, str)
                    or bool(code) == bool(supplied_token)):
                raise ValueError()
        except (ValueError, AttributeError):
            raise web.HTTPBadRequest()
        valid = (self._login_links.pop(code, 0) > time.monotonic()) if code else hmac.compare_digest(
            supplied_token.encode(), self.bot.settings.dashboard_token.encode()
        )
        if not valid:
            raise web.HTTPUnauthorized(
                text="Link expired or already used. Request a new one with uwu owner."
            )
        return web.json_response({"token": self.security.issue_session(), "expires_in": SESSION_SECONDS})

    async def logout(self, request):
        self.security.revoke(request.headers.get("Authorization", "")[7:])
        return web.json_response({"ok": True})

    async def window_login(self, request):
        try:
            body = await request.json()
            guild_id = int(body['guild_id'])
            if not 0 < guild_id < 2**64:
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise web.HTTPBadRequest(text='Invalid server ID')
        if self.bot.get_guild(guild_id) is None:
            raise web.HTTPNotFound(text='Server not found')
        now = time.monotonic()
        self._login_links = {key: expiry for key, expiry in self._login_links.items() if expiry > now}
        if len(self._login_links) >= 10:
            raise web.HTTPTooManyRequests(text='Too many pending windows; retry shortly.')
        code = secrets.token_urlsafe(32)
        self._login_links[code] = now + 60
        return web.json_response({'url': f'/?server={guild_id}#login={code}'})

    async def blacklist(self, request):
        from bot.models.chat_blacklist import ChatBlacklist

        async with self.bot.db_session() as session:
            rows = (
                await session.scalars(
                    select(ChatBlacklist).order_by(ChatBlacklist.updated_at.desc()).limit(200)
                )
            ).all()
        items = [dict(guild_id=str(row.guild_id), user_id=str(row.user_id),
                      active=row.active, reason=row.reason, source=row.source,
                      updated_at=row.updated_at.isoformat()) for row in rows]
        await self._add_member_identities(items)
        return web.json_response(
            {
                "items": items
            }
        )

    async def update_blacklist(self, request):
        try:
            body = await request.json()
            guild_id, user_id = int(body["guild_id"]), int(body["user_id"])
            active = body["active"]
            reason = body.get("reason", "Owner dashboard review")
            if (
                not 0 < guild_id < 2**63
                or not 0 < user_id < 2**63
                or not isinstance(active, bool)
                or not isinstance(reason, str)
            ):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise web.HTTPBadRequest(text="Invalid blacklist change")
        if self.bot.get_guild(guild_id) is None:
            raise web.HTTPNotFound(text="Server not found")
        await self.bot.chat_blacklist.set(
            guild_id, user_id, active=active, reason=reason, actor_id=715925710849572904
        )
        return web.json_response({"ok": True})

    async def index(self, request):
        return web.FileResponse(
            Path(__file__).with_name("index.html"),
            headers={"Content-Type": "text/html; charset=utf-8"},
        )

    async def avatar(self, request):
        return web.FileResponse(Path(__file__).parents[1] / "assets/listing/chat-meyaya.jpg")

    async def script(self, request):
        return web.FileResponse(
            Path(__file__).with_name("dashboard.js"),
            headers={"Content-Type": "application/javascript; charset=utf-8"},
        )

    async def style(self, request):
        return web.FileResponse(
            Path(__file__).with_name("dashboard.css"),
            headers={"Content-Type": "text/css; charset=utf-8"},
        )

    async def _identities(self):
        return await self._data_cache.get("identities", self._read_identities, 60)

    async def _read_identities(self):
        from sqlalchemy import union
        from bot.models.usage import GuildUsage
        from bot.models.request_log import RequestLog
        from bot.models.chat_blacklist import ChatBlacklist
        identities = await saved_identities(self.bot.db_session)
        async with self.bot.db_session() as session:
            ids = await session.scalars(union(*(select(model.guild_id) for model in (
                GuildSettings, GuildUsage, RequestLog, BotMemory, MeyayaUserState, ChatBlacklist))))
            for gid in ids:
                if gid is not None:
                    identities.setdefault(gid, dict(id=str(gid), name=f'Server {gid}',
                        owner_id=None, owner_name=None, icon_url=None))
        return identities

    async def _saved_server(self, guild_id):
        identities = await self._identities()
        return identities.get(guild_id)

    async def _known_server(self, guild_id):
        return self.bot.get_guild(guild_id) is not None or await self._saved_server(guild_id) is not None

    async def servers(self, request):
        return web.json_response(await self._server_data())

    async def _server_data(self):
        return await self._data_cache.get("servers", self._build_server_data, 15)

    async def _build_server_data(self):
        usage_report, saved, voice_totals = await asyncio.gather(
            self.bot.usage.report(), self._identities(), self._voice_totals())
        usage, limits = usage_report
        rows = await server_report(self.bot, usage_report=usage_report)
        live_ids = {int(row['id']) for row in rows}
        for row in rows:
            row['membership'] = 'current'
            for key in ('joined_at', 'left_at', 'last_activity_at'):
                row[key] = saved.get(int(row['id']), {}).get(key)
            guild = self.bot.get_guild(int(row['id']))
            if guild and guild.me and guild.me.joined_at:
                row['joined_at'] = guild.me.joined_at.isoformat()
            if not row.get('owner_name'):
                row['owner_name'] = saved.get(int(row['id']), {}).get('owner_name')
        for gid, identity in saved.items():
            if gid not in live_ids:
                rows.append(dict(identity, membership='removed', available=False,
                    prefix='uwu', autoresponder=False, limit=limits.get(gid, 40), exempt=False, model_success_rate=0, model_failures=0, model_average_latency_ms=None, model_tokens=0,
                    **usage.get(gid, dict(today_chats=0, today_commands=0, week_chats=0, week_commands=0))))
        for row in rows:
            row.update(voice_totals.get(int(row['id']), dict(today_voice_seconds=0,week_voice_seconds=0,total_voice_seconds=0)))
        return {'ready': self.bot.is_ready(), 'servers': rows}

    async def _voice_totals(self):
        from bot.services.voice_usage import report
        voice_cog = self.bot.get_cog('VoiceLiveCog')
        return await report(self.bot.db_session, getattr(voice_cog, '_sessions', {}).values())

    async def overview(self, request):
        from bot.web.insights import overview
        return web.json_response(overview(self.bot, (await self._server_data())["servers"]))

    async def server_insights(self, request):
        from bot.models.usage import GuildUsage
        try:
            gid = int(request.match_info['guild_id'])
            if not 0 < gid < 2**63:
                raise ValueError()
        except ValueError:
            raise web.HTTPBadRequest(text='Invalid server ID')
        if not await self._known_server(gid):
            raise web.HTTPNotFound(text='Server not found')
        async with self.bot.db_session() as session:
            events = (await session.scalars(select(GuildEvent).where(GuildEvent.guild_id == gid)
                .order_by(GuildEvent.occurred_at.desc(), GuildEvent.id.desc()).limit(100))).all()
            daily = (await session.scalars(select(GuildUsage).where(GuildUsage.guild_id == gid,
                GuildUsage.day >= datetime.now(UTC).date()-timedelta(days=13)).order_by(GuildUsage.day))).all()
        errors = [row for row in reversed(list(health_telemetry.errors.values())) if str(row.get('guild_id')) == str(gid)][:20]
        return web.json_response(dict(history=[dict(id=row.id, type=row.event_type,
            timestamp=row.occurred_at.isoformat(), actor=row.actor, details=row.details) for row in events],
            trend=[dict(day=row.day.isoformat(), chats=row.chats, commands=row.commands) for row in daily],
            errors=errors, identity=await self._saved_server(gid)))

    async def requests(self, request):
        try:
            guild_id = int(request.match_info["guild_id"])
            before = int(request.query["before"]) if "before" in request.query else None
            if guild_id <= 0 or (before is not None and not 0 < before < 2**63):
                raise ValueError()
        except ValueError:
            raise web.HTTPBadRequest(text="Invalid server or pagination cursor")
        if not await self._known_server(guild_id):
            raise web.HTTPNotFound(text="Server not found")
        kind = request.query.get('kind', 'all')
        if kind not in {'all', 'direct', 'automatic'}:
            raise web.HTTPBadRequest(text='Invalid conversation filter')
        data = await self.bot.request_log.page(guild_id, before, kind=kind)
        await self._add_member_identities(data['items'], guild_id=guild_id)
        return web.json_response(data)

    async def command_history(self, request):
        try:
            guild_id = int(request.match_info['guild_id'])
            before = int(request.query['before']) if request.query.get('before') else None
            if not 0 < guild_id < 2**63 or (before is not None and not 0 < before < 2**63):
                raise ValueError()
        except ValueError:
            raise web.HTTPBadRequest(text='Invalid server or cursor')
        if not await self._known_server(guild_id):
            raise web.HTTPNotFound(text='Server not found')
        return web.json_response(await self.bot.request_log.page(guild_id, before, kind='command'))

    async def server_details(self, request):
        try:
            guild_id = int(request.match_info["guild_id"])
            if not 0 < guild_id < 2**64:
                raise ValueError()
        except ValueError:
            raise web.HTTPBadRequest(text="Invalid server ID")
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            saved = await self._saved_server(guild_id)
            if saved:
                return web.json_response(dict(saved, stale=True, available=False, source='Last-known server identity'))
            raise web.HTTPNotFound(text="Server not found")
        info = cached_server_info(guild)
        await self._fill_owner(info, guild)
        if getattr(request, "query", {}).get("members") == "1":
            info.update(await self._member_preview(guild))
        else:
            info.update(member_preview=cached_member_preview(guild.members), member_preview_lazy=True)
        return web.json_response(info)

    async def _fill_owner(self, info, guild):
        if not info['owner_name'] and guild.owner_id:
            async with self._owner_lock:
                now = time.monotonic()
                entry = self._owner_names.get(guild.id)
                if entry is None or now >= entry[0]:
                    owner = self.bot.get_user(guild.owner_id)
                    if owner is None:
                        try:
                            owner = await asyncio.wait_for(self.bot.fetch_user(guild.owner_id), timeout=3)
                        except (discord.HTTPException, TimeoutError):
                            owner = None
                    self._owner_names = {gid: row for gid, row in self._owner_names.items() if row[0] > now}
                    entry = (now + 300, owner)
                    self._owner_names[guild.id] = entry
                if entry[1]:
                    info.update(owner_name=entry[1].display_name, owner_username=entry[1].name)

    async def server_summary(self, request):
        try:
            guild_id = int(request.match_info['guild_id'])
            if not 0 < guild_id < 2**64:
                raise ValueError()
        except ValueError:
            raise web.HTTPBadRequest(text='Invalid server ID')
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            saved = await self._saved_server(guild_id)
            if saved:
                return web.json_response(dict(saved, stale=True, available=False, source='Last-known server identity'))
            raise web.HTTPNotFound(text='Server not found')
        info = {'id': str(guild.id), 'name': guild.name, 'owner_id': str(guild.owner_id),
                'owner_name': guild.owner.display_name if guild.owner else None,
                'icon_url': str(guild.icon.url) if guild.icon else None}
        await self._fill_owner(info, guild)
        return web.json_response(info)

    async def server_commands(self, request):
        try:
            guild_id = int(request.match_info['guild_id'])
            if not 0 < guild_id < 2**64:
                raise ValueError()
        except ValueError:
            raise web.HTTPBadRequest(text='Invalid server ID')
        if not await self._known_server(guild_id):
            raise web.HTTPNotFound(text='Server not found')
        return web.json_response(await self.bot.usage.command_report(guild_id))

    async def _member_preview(self, guild):
        members = guild.members
        if sum(not member.bot for member in members) >= 50 or (guild.member_count is not None and len(members) >= guild.member_count):
            return {'member_preview': cached_member_preview(members)}
        async with self._member_lock:
            now = time.monotonic()
            entry = self._member_previews.get(guild.id)
            if entry and now < entry[0]:
                return entry[1]
            try:
                async with asyncio.timeout(5):
                    # One bounded page; filter bots before selecting 50 humans.
                    fetched = [member async for member in guild.fetch_members(limit=200)]
                result = {'member_preview': cached_member_preview(fetched)}
            except (discord.HTTPException, discord.ClientException, TimeoutError):
                result = {'member_preview': cached_member_preview(members),
                          'member_preview_error': 'Could not load all 50 members. Check bot access and Server Members Intent.'}
            self._member_previews = {gid: row for gid, row in self._member_previews.items() if row[0] > now}
            self._member_previews[guild.id] = (now + 300, result)
            return result

    async def operations(self, request):
        raw_guild_id = request.query.get("guild_id", "").strip()
        try:
            guild_id = int(raw_guild_id) if raw_guild_id else None
        except ValueError:
            raise web.HTTPBadRequest(text="Invalid server filter")
        if guild_id is not None:
            if guild_id <= 0:
                raise web.HTTPBadRequest(text="Invalid server filter")
            if self.bot.get_guild(guild_id) is None:
                raise web.HTTPNotFound(text="Server not found")
        return web.json_response(operational_telemetry.snapshot(guild_id))

    async def health(self, request):
        return web.json_response(await self.owner_health.snapshot())

    async def errors(self, request):
        error_id = request.query.get('id', '').strip().upper()
        if error_id and not re.fullmatch(r'MY-[A-F0-9]{8}', error_id):
            raise web.HTTPBadRequest(text='Invalid error ID')
        items = health_telemetry.search(error_id)
        if error_id and not items:
            async with self._error_search_lock:
                now = time.monotonic()
                cached = self._error_search_cache.get(error_id)
                if cached and cached[0] > now:
                    items = cached[1]
                else:
                    item = await asyncio.to_thread(find_retained_error, error_id)
                    items = [item] if item else []
                    self._error_search_cache = {key: value for key, value in self._error_search_cache.items()
                                                if value[0] > now}
                    if len(self._error_search_cache) >= 32:
                        self._error_search_cache.clear()
                    self._error_search_cache[error_id] = (now + 30, items)
        return web.json_response({'items': items, 'scope': 'process-and-retained-logs',
                                  'capacity': health_telemetry.capacity})

    async def safety(self, request):
        settings = self.bot.settings
        return web.json_response(
            {
                "enabled": settings.ai_enabled,
                "active_requests": self.bot.ai_guard.active,
                "max_concurrent": settings.ai_max_concurrent,
                "active_voice_sessions": len(self.bot.ai_guard.voice_guilds),
                "max_voice_sessions": settings.voice_max_sessions,
                "member_cooldown_seconds": settings.ai_user_cooldown_seconds,
            }
        )

    @staticmethod
    def _query_options(request, *, statuses: set[str] | None = None):
        try:
            guild_id = int(request.query["guild_id"]) if request.query.get("guild_id") else None
            limit = int(request.query.get("limit", "50"))
            offset = int(request.query.get("offset", "0"))
        except ValueError:
            raise web.HTTPBadRequest(text="Invalid dashboard filter")
        query = request.query.get("q", "").strip()
        status = request.query.get("status", "all").strip().lower()
        if (
            (guild_id is not None and guild_id <= 0)
            or not 1 <= limit <= 100
            or not 0 <= offset <= 100000
            or len(query) > 120
            or (statuses is not None and status not in statuses | {"all"})
            or (statuses is None and status != "all")
        ):
            raise web.HTTPBadRequest(text="Invalid dashboard filter")
        return guild_id, limit, offset, query, status

    def _cached_member_identity(self, guild_id, user_id, fallback=None):
        guild = self.bot.get_guild(guild_id) if guild_id else None
        member = getattr(guild, 'get_member', lambda _: None)(user_id) if guild else None
        user = member or getattr(self.bot, 'get_user', lambda _: None)(user_id)
        if user is None:
            entry = self._member_names.get(user_id)
            if entry and entry[0] > time.monotonic():
                user = entry[1]
        return {'user_name': fallback or getattr(user, 'display_name', None) or f'User {user_id}',
                'user_username': getattr(user, 'name', None)}

    async def _add_member_identities(self, items, *, guild_id=None):
        """Enrich old records by stable ID; never guess a handle from a nickname."""
        recorded_names = {id(item): item.get('user_name') for item in items}
        missing = set()
        for item in items:
            uid = int(item['user_id'])
            gid = guild_id if guild_id is not None else int(item['guild_id'])
            identity = self._cached_member_identity(gid, uid, item.get('user_name'))
            item.update(identity)
            entry = self._member_names.get(uid)
            if not identity['user_username'] and not (entry and entry[0] > time.monotonic()):
                missing.add(uid)
        fetch = getattr(self.bot, 'fetch_user', None)
        if fetch is None or not missing:
            return

        async def lookup(uid):
            async with self._member_name_slots:
                try:
                    user = await fetch(uid)
                except (discord.HTTPException, TimeoutError):
                    user = None
                self._member_names[uid] = (time.monotonic() + (300 if user else 30), user)
                while len(self._member_names) > 512:
                    self._member_names.pop(next(iter(self._member_names)))
        try:
            # Exact-user reads only. Page loading never fetches a whole guild,
            # spawns background work, or waits indefinitely on Discord limits.
            async with asyncio.timeout(2.5):
                await asyncio.gather(*(lookup(uid) for uid in sorted(missing)[:8]))
        except TimeoutError:
            pass
        for item in items:
            gid = guild_id if guild_id is not None else int(item['guild_id'])
            item.update(self._cached_member_identity(gid, int(item['user_id']), recorded_names[id(item)]))

    def _member_label(self, guild_id: int | None, user_id: int, fallback: str | None = None):
        guild = self.bot.get_guild(guild_id) if guild_id else None
        member = guild.get_member(user_id) if guild else None
        return member.display_name if member else (fallback or f"User {user_id}")

    def _guild_label(self, guild_id: int | None):
        if guild_id is None:
            return "Direct messages"
        guild = self.bot.get_guild(guild_id)
        return guild.name if guild else f"Server {guild_id}"

    async def memories(self, request):
        statuses = {item.value for item in MemoryStatus}
        guild_id, limit, offset, query, status = self._query_options(request, statuses=statuses)
        filters = []
        if guild_id is not None:
            if not await self._known_server(guild_id):
                raise web.HTTPNotFound(text="Server not found")
            filters.append(BotMemory.guild_id == guild_id)
        if status != "all":
            filters.append(BotMemory.status == status)
        if query:
            pattern = f"%{query}%"
            filters.append(
                or_(
                    cast(BotMemory.user_id, String).ilike(pattern),
                    BotMemory.source_user_name.ilike(pattern),
                    BotMemory.category.ilike(pattern),
                    BotMemory.subject.ilike(pattern),
                    BotMemory.relation.ilike(pattern),
                    BotMemory.value.ilike(pattern),
                )
            )
        async with self.bot.db_session() as session:
            total = await session.scalar(select(func.count(BotMemory.id)).where(*filters))
            records = (
                await session.scalars(
                    select(BotMemory)
                    .where(*filters)
                    .order_by(BotMemory.updated_at.desc(), BotMemory.id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
        items = []
        for record in records:
            source_url = None
            if record.guild_id and record.channel_id and record.source_message_id:
                source_url = (
                    f"https://discord.com/channels/{record.guild_id}/"
                    f"{record.channel_id}/{record.source_message_id}"
                )
            items.append(
                {
                    "id": record.id,
                    "guild_id": str(record.guild_id) if record.guild_id else None,
                    "guild_name": self._guild_label(record.guild_id),
                    "user_id": str(record.user_id),
                    "user_name": self._member_label(
                        record.guild_id, record.user_id, record.source_user_name
                    ),
                    "category": record.category,
                    "subject": record.subject,
                    "relation": record.relation,
                    "value": record.value,
                    "confidence": round(record.confidence * 100),
                    "status": record.status,
                    "conflict_value": record.conflict_value,
                    "lifecycle_reason": record.lifecycle_reason,
                    "conversation_summary": record.conversation_summary,
                    "source_url": source_url,
                    "created_at": record.created_at.isoformat() if record.created_at else None,
                    "updated_at": record.updated_at.isoformat() if record.updated_at else None,
                    "last_confirmed_at": (
                        record.last_confirmed_at.isoformat() if record.last_confirmed_at else None
                    ),
                }
            )
        return web.json_response(
            {
                "items": items,
                "total": int(total or 0),
                "next_offset": (
                    offset + len(items) if offset + len(items) < int(total or 0) else None
                ),
            }
        )

    async def nicknames(self, request):
        guild_id, limit, offset, query, _ = self._query_options(request)
        filters = [MeyayaUserState.nickname.is_not(None), MeyayaUserState.nickname != ""]
        if guild_id is not None:
            if not await self._known_server(guild_id):
                raise web.HTTPNotFound(text="Server not found")
            filters.append(MeyayaUserState.guild_id == guild_id)
        if query:
            pattern = f"%{query}%"
            filters.append(
                or_(
                    cast(MeyayaUserState.user_id, String).ilike(pattern),
                    MeyayaUserState.nickname.ilike(pattern),
                )
            )
        async with self.bot.db_session() as session:
            total = await session.scalar(
                select(func.count()).select_from(MeyayaUserState).where(*filters)
            )
            records = (
                await session.scalars(
                    select(MeyayaUserState)
                    .where(*filters)
                    .order_by(MeyayaUserState.updated_at.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
        items = [
            {
                "guild_id": str(record.guild_id),
                "guild_name": self._guild_label(record.guild_id),
                "user_id": str(record.user_id),
                "user_name": self._member_label(record.guild_id, record.user_id),
                "nickname": record.nickname,
                "familiarity": record.familiarity,
                "affection": record.affection,
                "annoyance": record.annoyance,
                "updated_at": record.updated_at.isoformat() if record.updated_at else None,
            }
            for record in records
        ]
        return web.json_response(
            {
                "items": items,
                "total": int(total or 0),
                "next_offset": (
                    offset + len(items) if offset + len(items) < int(total or 0) else None
                ),
            }
        )

    async def reset_usage(self, request):
        from bot.services.usage import UsageService
        from sqlalchemy import text
        try:
            guild_id = int(request.match_info['guild_id'])
            body = await request.json()
        except (TypeError, ValueError):
            raise web.HTTPBadRequest(text='Invalid request')
        if body != {'confirm': True} or type(body.get('confirm')) is not bool:
            raise web.HTTPBadRequest(text='Confirm resetting today\'s chat usage')
        if self.bot.get_guild(guild_id) is None:
            raise web.HTTPNotFound(text='Meyaya is not in this server')
        async with self.bot.db_session() as session:
            await session.execute(text('SELECT pg_advisory_xact_lock(:gid)'), {'gid': guild_id})
            result = await UsageService.reset_today(session, guild_id)
            session.add(GuildEvent(guild_id=guild_id, event_type='usage_reset',
                actor=request.get('dashboard_actor', 'local owner'), details=result))
            await session.commit()
        self._data_cache.clear()
        return web.json_response(dict(saved=True, **result))

    async def update(self, request):
        from bot.cogs.admin import normalize_prefix

        try:
            guild_id = int(request.match_info["guild_id"])
            data = await request.json()
        except (ValueError, TypeError):
            raise web.HTTPBadRequest(text="Invalid request")
        if self.bot.get_guild(guild_id) is None:
            raise web.HTTPNotFound(text="Server not found")
        if not isinstance(data, dict) or not {"prefix", "autoresponder", "limit"} <= set(data) or set(data) - {"prefix", "autoresponder", "limit", "features"}:
            raise web.HTTPBadRequest(text="Expected prefix, autoresponder and limit")
        features = data.get('features', {})
        if not isinstance(features, dict) or set(features) - FEATURES.keys() or any(type(value) is not bool for value in features.values()):
            raise web.HTTPBadRequest(text="Features must contain known feature names and true/false values")
        prefix = normalize_prefix(data["prefix"]) if isinstance(data["prefix"], str) else None
        if (
            prefix is None
            or type(data["autoresponder"]) is not bool
            or type(data["limit"]) is not int
            or not 0 <= data["limit"] <= 10000
        ):
            raise web.HTTPBadRequest(
                text="Invalid settings: limit must be 0-10000 and prefix 1-10 supported characters"
            )
        data["prefix"] = prefix
        async with self.bot.db_session() as session:
            # Serialize dashboard edits and retain the previous settings atomically.
            from sqlalchemy import text
            await session.execute(text('SELECT pg_advisory_xact_lock(:gid)'), {'gid': guild_id})
            previous = await session.get(GuildSettings, guild_id)
            before = dict(prefix=previous.command_prefix if previous else 'uwu',
                limit=previous.daily_chat_limit if previous else 40,
                autoresponder=previous.autoresponder_enabled if previous else False)
            values = {
                "command_prefix": prefix,
                "autoresponder_enabled": data["autoresponder"],
                "daily_chat_limit": data["limit"],
            }
            disabled = set(getattr(previous, 'disabled_features', None) or ())
            if 'features' in data:
                before['features'] = feature_states(disabled)
                for name, enabled in features.items():
                    if enabled:
                        disabled.discard(name)
                    else:
                        disabled.add(name)
                values['disabled_features'] = sorted(disabled)
                data['features'] = feature_states(disabled)
            await session.execute(
                insert(GuildSettings)
                .values(guild_id=guild_id, **values)
                .on_conflict_do_update(index_elements=[GuildSettings.guild_id], set_=values)
            )
            session.add(GuildEvent(guild_id=guild_id, event_type='settings_changed',
                actor=request.get('dashboard_actor', 'local owner'),
                details={'before': before, 'after': data}))
            await session.commit()
        self._data_cache.clear()
        self.bot.cache_guild_prefix(guild_id, prefix)
        self.bot.cache_autoresponder(guild_id, data["autoresponder"])
        if 'features' in data:
            self.bot.cache_guild_features(guild_id, disabled)
        logger.info("Owner dashboard updated settings for guild=%s", guild_id)
        return web.json_response({"saved": True})

    async def start(self):
        self.security.validate_config()
        self.runner = web.AppRunner(self.app, access_log=None)
        await self.runner.setup()
        try:
            await web.TCPSite(
                self.runner,
                self.bot.settings.dashboard_host,
                int(os.environ.get("PORT", self.bot.settings.dashboard_port)),
            ).start()
        except BaseException:
            await self.runner.cleanup()
            raise
        logger.info(
            "Owner dashboard listening on %s:%s",
            self.bot.settings.dashboard_host,
            self.bot.settings.dashboard_port,
        )

    async def close(self):
        self.security.sessions.clear()
        self._login_links.clear()
        if self.runner:
            await self.runner.cleanup()
