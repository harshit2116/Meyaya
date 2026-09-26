"""Local-first owner dashboard using the existing aiohttp dependency."""

import hmac
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
from bot.models.memory import BotMemory, MemoryStatus
from bot.models.meyaya_state import MeyayaUserState
from bot.web.security import DashboardSecurity, SESSION_SECONDS

logger = logging.getLogger(__name__)


async def server_report(bot):
    usage, limits = await bot.usage.report()
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
                "available": not guild.unavailable,
                "readable_channels": accessible,
                "can_timeout": bool(permissions and permissions.moderate_members),
                "prefix": bot.prefix_for_guild(guild.id),
                "autoresponder": bot.autoresponder_enabled(guild.id),
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
    def __init__(self, bot):
        self.bot = bot
        self.runner = None
        self._login_links = {}
        self.security = DashboardSecurity(bot.settings)
        token = bot.settings.dashboard_token
        if len(token) < 32:
            raise ValueError("DASHBOARD_TOKEN must contain at least 32 random characters")

        @web.middleware
        async def security(request, handler):
            try:
                self.security.check_request(request)
                if request.path.startswith("/api/"):
                    if request.path == "/api/login":
                        self.security.throttle(request.remote)
                    else:
                        supplied = request.headers.get("Authorization", "")
                        if not supplied.startswith("Bearer ") or not self.security.authenticated(supplied[7:]):
                            self.security.throttle(request.remote)
                            raise web.HTTPUnauthorized(text="Owner session expired or missing")
                    if request.method not in {"GET", "HEAD"} and request.content_type != "application/json":
                        raise web.HTTPUnsupportedMediaType()
                response = await handler(request)
            except web.HTTPException as error:
                response = web.Response(status=error.status, headers=error.headers, body=error.body)
            except SQLAlchemyError:
                logger.warning("Dashboard database operation unavailable")
                response = web.json_response(
                    {"error": "Database unavailable; please retry."}, status=503
                )
            except Exception as error:
                # Never echo request bodies, credentials, or database errors.
                logger.error("Dashboard request failed (%s)", type(error).__name__)
                response = web.json_response({"error": "Request unavailable; please retry."}, status=500)
            response.headers.update(
                {
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                    "X-Frame-Options": "DENY",
                    "Referrer-Policy": "no-referrer",
                    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'; form-action 'self'",
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
        self.app.router.add_get("/api/blacklist", self.blacklist)
        self.app.router.add_patch("/api/blacklist", self.update_blacklist)
        self.app.router.add_get("/dashboard.js", self.script)
        self.app.router.add_get("/dashboard.css", self.style)
        self.app.router.add_get("/api/servers", self.servers)
        self.app.router.add_get("/api/servers/{guild_id}/requests", self.requests)
        self.app.router.add_get("/api/memories", self.memories)
        self.app.router.add_get("/api/nicknames", self.nicknames)
        self.app.router.add_get("/api/operations", self.operations)
        self.app.router.add_get("/api/safety", self.safety)
        self.app.router.add_patch("/api/servers/{guild_id}", self.update)

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

    async def blacklist(self, request):
        from bot.models.chat_blacklist import ChatBlacklist

        async with self.bot.db_session() as session:
            rows = (
                await session.scalars(
                    select(ChatBlacklist).order_by(ChatBlacklist.updated_at.desc()).limit(200)
                )
            ).all()
        return web.json_response(
            {
                "items": [
                    {
                        "guild_id": str(row.guild_id),
                        "user_id": str(row.user_id),
                        "active": row.active,
                        "reason": row.reason,
                        "source": row.source,
                        "updated_at": row.updated_at.isoformat(),
                    }
                    for row in rows
                ]
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
        return web.Response(
            text=Path(__file__).with_name("index.html").read_text(encoding="utf-8"),
            content_type="text/html",
        )

    async def script(self, request):
        return web.Response(
            text=Path(__file__).with_name("dashboard.js").read_text(encoding="utf-8"),
            content_type="application/javascript",
        )

    async def style(self, request):
        return web.Response(
            text=Path(__file__).with_name("dashboard.css").read_text(encoding="utf-8"),
            content_type="text/css",
        )

    async def servers(self, request):
        return web.json_response(
            {"ready": self.bot.is_ready(), "servers": await server_report(self.bot)}
        )

    async def requests(self, request):
        try:
            guild_id = int(request.match_info["guild_id"])
            before = int(request.query["before"]) if "before" in request.query else None
            if guild_id <= 0 or (before is not None and not 0 < before < 2**63):
                raise ValueError()
        except ValueError:
            raise web.HTTPBadRequest(text="Invalid server or pagination cursor")
        if self.bot.get_guild(guild_id) is None:
            raise web.HTTPNotFound(text="Server not found")
        return web.json_response(await self.bot.request_log.page(guild_id, before))

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
            if self.bot.get_guild(guild_id) is None:
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
            if self.bot.get_guild(guild_id) is None:
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

    async def update(self, request):
        from bot.cogs.admin import normalize_prefix

        try:
            guild_id = int(request.match_info["guild_id"])
            data = await request.json()
        except (ValueError, TypeError):
            raise web.HTTPBadRequest(text="Invalid request")
        if self.bot.get_guild(guild_id) is None:
            raise web.HTTPNotFound(text="Server not found")
        if not isinstance(data, dict) or set(data) != {"prefix", "autoresponder", "limit"}:
            raise web.HTTPBadRequest(text="Expected prefix, autoresponder and limit")
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
        async with self.bot.db_session() as session:
            values = {
                "command_prefix": prefix,
                "autoresponder_enabled": data["autoresponder"],
                "daily_chat_limit": data["limit"],
            }
            await session.execute(
                insert(GuildSettings)
                .values(guild_id=guild_id, **values)
                .on_conflict_do_update(index_elements=[GuildSettings.guild_id], set_=values)
            )
            await session.commit()
        self.bot.cache_guild_prefix(guild_id, prefix)
        self.bot.cache_autoresponder(guild_id, data["autoresponder"])
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
