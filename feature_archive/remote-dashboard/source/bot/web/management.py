"""API-only remote management listener, reached through a loopback tunnel."""

import asyncio
from collections import deque
from contextlib import suppress
from datetime import UTC, datetime
import hmac
from ipaddress import ip_address
import json
import logging
import time
from urllib.parse import urlsplit

from aiohttp import web, WSMsgType
from bot.logging.health import health
from bot.logging.telemetry import operations, event
from bot.web.dashboard import Dashboard
from bot.web.dashboard_events import hub
from bot.web.dashboard_sanitizer import sanitize, secret_values

logger = logging.getLogger(__name__)


class ManagementAPI(Dashboard):
    def __init__(self, bot):
        super().__init__(bot, api_only=True)
        self.secrets = secret_values(bot.settings)
        self.token = bot.settings.dashboard_api_token
        if len(self.token) < 32 or not self.token.isascii():
            raise ValueError("A random ASCII dashboard API token is required")
        for name in ("discord_token", "gemini_api_key", "klipy_api_key", "dashboard_token"):
            if self.token == getattr(bot.settings, name, None):
                raise ValueError("Dashboard API credential must be independent")
        self.origin = bot.settings.dashboard_api_origin.rstrip("/")
        if self.origin:
            parsed = urlsplit(self.origin)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("API origin must be a plain HTTPS origin")
            _ = parsed.port
        self.rate = deque(maxlen=120)
        self.history = deque(maxlen=120)
        self.sockets = set()
        self.sampler = None
        self.previous_state = None
        self.app = web.Application(middlewares=[self.middleware], client_max_size=4096)
        get = self.app.router.add_get
        post = self.app.router.add_post
        # Existing owner interface, excluding login links and all static/HTML routes.
        for path, handler in (
            ("/api/servers", self.servers),
            ("/api/guilds", self.guilds),
            ("/api/servers/{guild_id}/details", self.server_details),
            ("/api/servers/{guild_id}/summary", self.server_summary),
            ("/api/servers/{guild_id}/commands", self.server_commands),
            ("/api/servers/{guild_id}/requests", self.requests),
            ("/api/memories", self.memories),
            ("/api/nicknames", self.nicknames),
            ("/api/blacklist", self.blacklist),
            ("/api/operations", self.operations),
            ("/api/safety", self.safety),
            ("/api/errors", self.errors),
            ("/api/errors/recent", self.errors),
            ("/api/health", self.health),
            ("/api/status", self.status),
            ("/api/stats", self.stats),
            ("/api/commands/recent", self.commands_recent),
            ("/api/voice/status", self.voice),
            ("/api/games/status", self.games),
            ("/api/cache/status", self.cache_status),
            ("/api/database/status", self.dependency),
            ("/api/redis/status", self.dependency),
            ("/ws/dashboard", self.websocket),
        ):
            get(path, handler)
        self.app.router.add_patch("/api/servers/{guild_id}", self.update)
        self.app.router.add_patch("/api/blacklist", self.update_blacklist)
        post("/api/guilds/{guild_id}/settings", self.update)
        post("/api/control/reload", self.reload_settings)
        post("/api/cache/clear", self.clear_cache)

    @web.middleware
    async def middleware(self, request, handler):
        try:
            if not ip_address(request.remote or "").is_loopback:
                raise web.HTTPForbidden()
            if request.headers.get("Origin") or request.headers.get("Sec-Fetch-Site"):
                raise web.HTTPForbidden(text="Server-to-server API only")
            expected = urlsplit(self.origin).netloc if self.origin else None
            if expected:
                if (
                    request.host.lower() != expected.lower()
                    or request.headers.get("X-Forwarded-Proto") != "https"
                ):
                    raise web.HTTPForbidden(text="Secure tunnel required")
            elif urlsplit("//" + request.host).hostname not in {"127.0.0.1", "localhost", "::1"}:
                raise web.HTTPForbidden()
            now = time.monotonic()
            while self.rate and now - self.rate[0] >= 60:
                self.rate.popleft()
            if len(self.rate) >= 120:
                raise web.HTTPTooManyRequests(headers={"Retry-After": "60"})
            self.rate.append(now)
            supplied = request.headers.get("Authorization", "")
            if not hmac.compare_digest(supplied.encode(), ("Bearer " + self.token).encode()):
                event("dashboard.authentication_failed")
                raise web.HTTPUnauthorized()
            if request.method not in {"GET", "HEAD"}:
                if not self.bot.settings.dashboard_allow_management:
                    raise web.HTTPForbidden(text="Remote management is disabled")
                if request.content_type != "application/json":
                    raise web.HTTPUnsupportedMediaType()
            if request.path == "/ws/dashboard":
                return await handler(request)
            async with asyncio.timeout(10):
                response = await handler(request)
            if response.content_type == "application/json":
                response = web.json_response(
                    sanitize(json.loads(response.text), self.secrets), status=response.status
                )
        except web.HTTPException as error:
            response = web.json_response(
                {"error": sanitize(error.text, self.secrets)},
                status=error.status,
                headers=(
                    {"Retry-After": error.headers.get("Retry-After", "60")}
                    if error.status == 429
                    else None
                ),
            )
        except Exception as error:
            error_id = health.capture(error, command="management_api", stage="request")
            event("dashboard.api_failed", error_id=error_id, exception=type(error).__name__)
            response = web.json_response(
                {"error": "Management request unavailable", "error_id": error_id}, status=503
            )
        response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
        return response

    def voice_snapshot(self):
        return {
            "active_connections": len(self.bot.voice_clients),
            "connections": [
                {
                    "guild_id": str(client.guild.id),
                    "channel_id": str(client.channel.id) if client.channel else None,
                    "connected": client.is_connected(),
                    "playing": client.is_playing(),
                }
                for client in self.bot.voice_clients
            ],
        }

    def games_snapshot(self):
        games = self.bot.get_cog("SocialGamesCog")
        return {
            "scope": "social-games",
            "guilds": [
                {
                    "guild_id": str(guild.id),
                    "active": games.sessions.active_count(guild.id) if games else 0,
                }
                for guild in self.bot.guilds
            ],
        }

    async def health(self, request):
        snapshot = await self.owner_health.snapshot()
        tasks = []
        for name in ("_dashboard_settings_refresh", "_request_log_maintenance"):
            task = getattr(self.bot, name, None)
            tasks.append(
                {
                    "name": name.lstrip("_"),
                    "status": "healthy" if task and not task.done() else "unavailable",
                }
            )
        voice_cog = self.bot.get_cog("VoiceLiveCog")
        watcher = getattr(voice_cog, "_empty_watch", None)
        if watcher is not None:
            tasks.append(
                {
                    "name": "Voice watcher",
                    "status": (
                        "healthy"
                        if watcher.is_running() and not watcher.failed()
                        else "unavailable"
                    ),
                }
            )
        host = snapshot["host"]
        reasons = [
            row["name"] for row in snapshot["dependencies"] if row["status"] == "unavailable"
        ]
        degraded = []
        for row in snapshot["dependencies"]:
            if (row.get("latency_ms") or 0) > 1000:
                degraded.append(row["name"] + " latency")
        if any(row["status"] != "healthy" for row in tasks):
            degraded.append("Background tasks")
        if any(row["status"] in {"degraded", "unavailable"} for row in snapshot["models"]):
            degraded.append("AI provider")
        if (host.get("wake_lag_ms") or 0) > 250:
            degraded.append("Event loop lag")
        memory_percent = None
        if host.get("rss_mb") is not None and host.get("memory_limit_mb"):
            memory_percent = round(host["rss_mb"] * 100 / host["memory_limit_mb"], 1)
            if memory_percent >= 85:
                degraded.append("Memory pressure")
        if (host.get("throttle_percent") or 0) >= 10 or (host.get("cpu_percent") or 0) >= 45:
            degraded.append("CPU pressure")
        if time.time() - host.get("observed_at", 0) > 150:
            degraded.append("Host metrics stale")
        rows = [
            row
            for row in operations._commands
            if time.time() - datetime.fromisoformat(row["timestamp"]).timestamp() < 3600
        ]
        failed = sum(row["status"] == "error" for row in rows)
        if len(rows) >= 10 and failed / len(rows) > 0.1:
            degraded.append("Command error rate")
        voice = self.voice_snapshot()
        if any(not row["connected"] for row in voice["connections"]):
            degraded.append("Voice disconnected")
        if any(not session.is_active for session in getattr(voice_cog, "_sessions", {}).values()):
            degraded.append("Voice provider not ready")
        snapshot.update(
            status="unhealthy" if reasons else ("degraded" if degraded else "healthy"),
            reasons=reasons + degraded,
            tasks=tasks,
            voice=voice,
            memory_percent=memory_percent,
            version=self.bot.settings.bot_version,
            commands={
                "executed_last_hour": len(rows),
                "errors_last_hour": failed,
                "scope": "bounded latest 2000 callbacks",
            },
            history=list(self.history),
        )
        return web.json_response(snapshot)

    async def status(self, request):
        return web.json_response(
            {
                "ready": self.bot.is_ready(),
                "guilds": len(self.bot.guilds),
                "version": self.bot.settings.bot_version,
                "uptime_seconds": round(time.time() - health.started_at),
            }
        )

    async def stats(self, request):
        return web.json_response(operations.snapshot())

    async def commands_recent(self, request):
        return web.json_response(operations.command_snapshot())

    async def guilds(self, request):
        response = await self.servers(request)
        data = json.loads(response.text)
        for row in data["servers"]:
            guild = self.bot.get_guild(int(row["id"]))
            row["permissions"] = (
                [name for name, allowed in guild.me.guild_permissions if allowed]
                if guild.me
                else []
            )
            channel = (getattr(self.bot, "_guild_chat_channels", None) or {}).get(guild.id)
            row["chat_channels"] = [str(channel)] if channel else []
        return web.json_response(data)

    async def voice(self, request):
        return web.json_response(self.voice_snapshot())

    async def games(self, request):
        return web.json_response(self.games_snapshot())

    async def cache_status(self, request):
        return web.json_response(
            {
                "discord_messages": len(getattr(self.bot, "cached_messages", ())),
                "health_history": len(self.history),
                "event_history": len(hub.history),
                "subscribers": len(hub.clients),
                "events_dropped": hub.dropped,
            }
        )

    async def dependency(self, request):
        data = await self.owner_health.snapshot()
        name = "PostgreSQL" if request.path == "/api/database/status" else "Redis"
        return web.json_response(next(row for row in data["dependencies"] if row["name"] == name))

    async def reload_settings(self, request):
        if await request.json() != {"action": "guild_settings"}:
            raise web.HTTPBadRequest(text="Only guild_settings reload is allowed")
        if await self.bot._load_guild_prefixes() is False:
            raise web.HTTPServiceUnavailable(text="Server settings could not be reloaded")
        return web.json_response({"reloaded": True})

    async def clear_cache(self, request):
        if await request.json() != {"scope": "dashboard"}:
            raise web.HTTPBadRequest(text="Only dashboard cache clearing is allowed")
        self.owner_health.cache = None
        self._error_search_cache.clear()
        self._member_previews.clear()
        self._owner_names.clear()
        return web.json_response({"cleared": True})

    async def websocket(self, request):
        try:
            queue = hub.subscribe()
        except ValueError:
            raise web.HTTPTooManyRequests()
        socket = web.WebSocketResponse(heartbeat=15, max_msg_size=4096, receive_timeout=45)
        writer = None
        try:
            await socket.prepare(request)
            self.sockets.add(socket)
            event("dashboard.websocket_connected")
            await socket.send_json(
                {"type": "snapshot", "events": sanitize(list(hub.history), self.secrets)}
            )

            async def send():
                while True:
                    try:
                        item = await asyncio.wait_for(queue.get(), 15)
                    except TimeoutError:
                        item = {"type": "heartbeat", "timestamp": datetime.now(UTC).isoformat()}
                    async with asyncio.timeout(5):
                        await socket.send_json(sanitize(item, self.secrets))

            writer = asyncio.create_task(send())
            # Also wake the reader if a slow/dead client's writer fails.
            writer.add_done_callback(lambda _: asyncio.create_task(socket.close()))
            async for message in socket:
                if message.type == WSMsgType.TEXT:
                    await socket.close(code=1008, message=b"Read-only stream")
                    break
        finally:
            hub.clients.discard(queue)
            self.sockets.discard(socket)
            if writer:
                writer.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await writer
            event("dashboard.websocket_disconnected")
        return socket

    async def sample(self):
        while True:
            try:
                data = json.loads((await self.health(None)).text)
                self.history.append(
                    {
                        key: data[key]
                        for key in ("generated_at", "status", "host", "commands", "dependencies")
                    }
                )
                if data["status"] != self.previous_state:
                    event("health.changed", status=data["status"])
                    self.previous_state = data["status"]
                event(
                    "bot.latency",
                    duration_ms=next(
                        row["latency_ms"]
                        for row in data["dependencies"]
                        if row["name"] == "Discord"
                    ),
                )
                for row in data["dependencies"]:
                    if row["name"] in {"Redis", "PostgreSQL"}:
                        event(
                            "redis.health" if row["name"] == "Redis" else "database.health",
                            status=row["status"],
                        )
            except Exception as error:
                event("dashboard.sample_failed", exception=type(error).__name__)
            await asyncio.sleep(15)

    async def start(self):
        self.runner = web.AppRunner(self.app, access_log=None)
        await self.runner.setup()
        await web.TCPSite(self.runner, "127.0.0.1", self.bot.settings.dashboard_api_port).start()
        self.sampler = asyncio.create_task(self.sample(), name="dashboard-health")
        event("dashboard.api_started")

    async def close(self):
        if self.sampler:
            self.sampler.cancel()
            with suppress(asyncio.CancelledError):
                await self.sampler
        for socket in tuple(self.sockets):
            await socket.close(code=1001, message=b"Bot shutting down")
        if self.runner:
            await self.runner.cleanup()
