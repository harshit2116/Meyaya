"""Local-first owner dashboard using the existing aiohttp dependency."""

import hmac
import logging
import os
from pathlib import Path
from aiohttp import web
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.dialects.postgresql import insert
from bot.models.guild_settings import GuildSettings

logger = logging.getLogger(__name__)


async def server_report(bot):
    usage, limits = await bot.usage.report()
    monitor = bot.get_cog("MonitorCog")
    games = bot.get_cog("SocialGamesCog")
    voice = bot.get_cog("VoiceLiveCog")
    rows = []
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
        token = bot.settings.dashboard_token
        if len(token) < 32:
            raise ValueError("DASHBOARD_TOKEN must contain at least 32 random characters")

        @web.middleware
        async def security(request, handler):
            if request.path.startswith("/api/"):
                supplied = request.headers.get("Authorization", "")
                if not hmac.compare_digest(supplied.encode(), ("Bearer " + token).encode()):
                    raise web.HTTPUnauthorized(text="Owner access required")
                # No cookie authentication or permissive CORS; mutations require a bearer token.
                if (
                    request.method not in {"GET", "HEAD"}
                    and request.content_type != "application/json"
                ):
                    raise web.HTTPUnsupportedMediaType()
            try:
                response = await handler(request)
            except SQLAlchemyError:
                logger.warning("Dashboard database operation unavailable")
                response = web.json_response(
                    {"error": "Database unavailable; please retry."}, status=503
                )
            response.headers.update(
                {
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                    "X-Frame-Options": "DENY",
                    "Referrer-Policy": "no-referrer",
                    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'",
                }
            )
            return response

        self.app = web.Application(middlewares=[security], client_max_size=4096)
        self.app.router.add_get("/", self.index)
        self.app.router.add_get("/dashboard.js", self.script)
        self.app.router.add_get("/dashboard.css", self.style)
        self.app.router.add_get("/api/servers", self.servers)
        self.app.router.add_get("/api/servers/{guild_id}/requests", self.requests)
        self.app.router.add_patch("/api/servers/{guild_id}", self.update)

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
        if self.runner:
            await self.runner.cleanup()
