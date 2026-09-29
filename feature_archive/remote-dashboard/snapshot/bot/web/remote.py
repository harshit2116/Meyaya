"""Laptop-only proxy: no Discord, database, Redis or provider credentials needed."""

import argparse
import asyncio
from collections import deque
from contextlib import suppress
from datetime import UTC, datetime
import json
import logging
import os
from pathlib import Path
import random
import secrets
from types import SimpleNamespace
from urllib.parse import urlsplit

import aiohttp
from aiohttp import web, WSMsgType
from dotenv import dotenv_values

from bot.web.dashboard import Dashboard
from bot.web.dashboard_sanitizer import sanitize

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
BROWSER_SOCKETS = web.AppKey("browser_sockets", set)
FIXED_GET = (
    "/api/health",
    "/api/status",
    "/api/guilds",
    "/api/stats",
    "/api/commands/recent",
    "/api/errors/recent",
    "/api/voice/status",
    "/api/games/status",
    "/api/cache/status",
    "/api/database/status",
    "/api/redis/status",
    "/api/servers",
    "/api/memories",
    "/api/nicknames",
    "/api/blacklist",
    "/api/operations",
    "/api/safety",
    "/api/errors",
)


def configuration(path):
    values = dotenv_values(path) if Path(path).is_file() else {}

    def read(name, default=""):
        return os.environ.get(name, values.get(name) or default)

    origin = read("MEYAYA_API_URL").rstrip("/")
    parsed = urlsplit(origin)
    if (
        not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
        or (
            parsed.scheme != "https"
            and not (
                parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
            )
        )
    ):
        raise ValueError(
            "MEYAYA_API_URL must be a plain HTTPS origin (HTTP loopback allowed for tests)"
        )
    _ = parsed.port
    token = read("DASHBOARD_API_TOKEN")
    if len(token) < 32 or not token.isascii():
        raise ValueError(
            "Set a separate random ASCII DASHBOARD_API_TOKEN of at least 32 characters"
        )
    headers = {"Authorization": "Bearer " + token}
    client, secret = read("CF_ACCESS_CLIENT_ID"), read("CF_ACCESS_CLIENT_SECRET")
    if bool(client) != bool(secret):
        raise ValueError("Both Cloudflare Access service credentials are required together")
    if client:
        headers.update({"CF-Access-Client-Id": client, "CF-Access-Client-Secret": secret})
    return origin, headers


class RemoteDashboard(Dashboard):
    def __init__(self, origin, headers, port=8080):
        settings = SimpleNamespace(
            dashboard_host="127.0.0.1",
            dashboard_port=port,
            dashboard_public_url="",
            dashboard_trusted_proxies="",
            dashboard_token=secrets.token_urlsafe(32),
        )
        super().__init__(SimpleNamespace(settings=settings), local_no_auth=True)
        self.origin = origin
        self.headers = dict(headers)
        self.redactions = tuple(headers.values()) + tuple(
            value.removeprefix("Bearer ") for value in headers.values()
        )
        self.session = None
        self.upstream_task = None
        self.clients = set()
        self.events = deque(maxlen=100)
        self.transport = {
            "api": "unknown",
            "websocket": "connecting",
            "last_event_at": None,
            "last_api_at": None,
        }
        self.app = web.Application(middlewares=[self.local_security], client_max_size=4096)
        self.app.router.add_get("/", self.index)
        self.app.router.add_get("/dashboard.js", self.script)
        self.app.router.add_get("/dashboard.css", self.style)
        for path in FIXED_GET:
            self.app.router.add_get(path, self.proxy)
        for suffix in ("details", "summary", "commands", "requests"):
            self.app.router.add_get("/api/servers/{guild_id:[0-9]+}/" + suffix, self.proxy)
        self.app.router.add_patch("/api/servers/{guild_id:[0-9]+}", self.proxy)
        self.app.router.add_patch("/api/blacklist", self.proxy)
        self.app.router.add_post("/api/guilds/{guild_id:[0-9]+}/settings", self.proxy)
        self.app.router.add_post("/api/control/reload", self.proxy)
        self.app.router.add_post("/api/cache/clear", self.proxy)
        self.app.router.add_get("/api/connection", self.connection)
        self.app.router.add_get("/ws/dashboard", self.websocket)
        self.app.on_startup.append(self.open_clients)
        self.app.on_cleanup.append(self.close_clients)
        self.app.on_shutdown.append(self.close_sockets)

    @web.middleware
    async def local_security(self, request, handler):
        try:
            self.security.check_request(request)
            if request.method not in {"GET", "HEAD"} and request.content_type != "application/json":
                raise web.HTTPUnsupportedMediaType()
            response = await handler(request)
        except web.HTTPException as error:
            response = web.json_response(
                {"error": sanitize(error.text, self.redactions)}, status=error.status
            )
        except Exception as error:
            logger.warning("Local dashboard request failed: %s", type(error).__name__)
            response = web.json_response({"error": "Local proxy unavailable"}, status=503)
        if isinstance(response, web.WebSocketResponse):
            return response
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'self'; connect-src 'self'; img-src 'self' https://cdn.discordapp.com; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'; form-action 'self'",
            }
        )
        return response

    async def index(self, request):
        response = await super().index(request)
        response.text = response.text.replace(
            "<body>", '<body data-local-dashboard="true" data-remote-dashboard="true">'
        )
        return response

    async def connection(self, request):
        return web.json_response(dict(self.transport))

    async def proxy(self, request):
        if len(request.query_string) > 2048:
            raise web.HTTPBadRequest(text="Query too long")
        # Only matched, literal routes reach here. No arbitrary URL/headers/redirects.
        body = await request.read() if request.method not in {"GET", "HEAD"} else None
        try:
            async with self.session.request(
                request.method,
                self.origin + request.path,
                params=request.query,
                headers={**self.headers, "Content-Type": "application/json"},
                data=body,
                allow_redirects=False,
            ) as response:
                if response.content_type != "application/json":
                    raise ValueError("Unexpected upstream response")
                raw = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    raw.extend(chunk)
                    if len(raw) > 2 * 1024 * 1024:
                        raise ValueError("Response too large")
                data = sanitize(json.loads(raw), self.redactions)
                self.transport["api"] = "connected" if response.status < 500 else "degraded"
                if response.status in {401, 403}:
                    self.transport["api"] = "authentication_failed"
                self.transport["last_api_at"] = datetime.now(UTC).isoformat()
                return web.json_response(data, status=response.status)
        except (aiohttp.ClientError, TimeoutError, ValueError):
            self.transport["api"] = "disconnected"
            return web.json_response(
                {"error": "Meyaya API unavailable. Check the tunnel, remote bot and credentials."},
                status=503,
            )

    def broadcast(self, item):
        item = sanitize(item, self.redactions)
        if item.get("type") != "heartbeat":
            self.events.append(item)
        for queue in tuple(self.clients):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(item)

    async def upstream(self):
        delay = 1
        while True:
            self.transport["websocket"] = "connecting"
            try:
                ws_options = (
                    {"timeout": aiohttp.ClientWSTimeout(ws_receive=40, ws_close=5)}
                    if hasattr(aiohttp, "ClientWSTimeout")
                    else {"receive_timeout": 40}
                )
                async with self.session.ws_connect(
                    self.origin + "/ws/dashboard",
                    headers=self.headers,
                    heartbeat=15,
                    max_msg_size=65536,
                    **ws_options,
                ) as socket:
                    self.transport["websocket"] = "connected"
                    logger.info("dashboard.websocket_connected")
                    self.broadcast({"type": "connection", **self.transport})
                    while True:
                        message = await socket.receive(timeout=40)
                        if message.type == WSMsgType.TEXT:
                            item = message.json()
                            if not isinstance(item, dict):
                                raise ValueError("Invalid event")
                            self.transport["last_event_at"] = datetime.now(UTC).isoformat()
                            delay = 1  # Reset backoff only after actual upstream traffic.
                            if item.get("type") == "snapshot":
                                self.events.clear()
                                for row in item.get("events", [])[-100:]:
                                    self.broadcast(row)
                            else:
                                self.broadcast(item)
                        elif message.type in {WSMsgType.CLOSED, WSMsgType.CLOSE, WSMsgType.ERROR}:
                            break
            except (aiohttp.ClientError, TimeoutError, ValueError):
                logger.warning("dashboard.websocket_reconnecting")
            self.transport["websocket"] = "reconnecting"
            self.broadcast({"type": "connection", **self.transport})
            await asyncio.sleep(delay + random.uniform(0, 0.5))
            delay = min(30, delay * 2)

    async def websocket(self, request):
        if len(self.clients) >= 8:
            raise web.HTTPTooManyRequests()
        socket = web.WebSocketResponse(heartbeat=15, max_msg_size=4096)
        queue = asyncio.Queue(maxsize=64)
        writer = None
        try:
            await socket.prepare(request)
            self.clients.add(queue)
            request.app[BROWSER_SOCKETS].add(socket)
            await socket.send_json(
                {"type": "snapshot", "events": list(self.events), "connection": self.transport}
            )

            async def send():
                while True:
                    async with asyncio.timeout(45):
                        item = await queue.get()
                    async with asyncio.timeout(5):
                        await socket.send_json(item)

            writer = asyncio.create_task(send())
            writer.add_done_callback(lambda _: asyncio.create_task(socket.close()))
            async for message in socket:
                if message.type == WSMsgType.TEXT:
                    await socket.close(code=1008)
        finally:
            self.clients.discard(queue)
            request.app[BROWSER_SOCKETS].discard(socket)
            if writer:
                writer.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await writer
        return socket

    async def open_clients(self, app):
        app[BROWSER_SOCKETS] = set()
        trace = aiohttp.TraceConfig()

        async def reject_redirect(session, context, params):
            # Includes the WebSocket handshake; do not forward Access credentials
            # to a redirect destination or an interactive Access login page.
            raise aiohttp.ClientError("Upstream redirects are not allowed")

        trace.on_request_redirect.append(reject_redirect)
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=12, connect=5),
            connector=aiohttp.TCPConnector(limit=6, limit_per_host=6),
            trust_env=False,
            trace_configs=[trace],
        )
        self.upstream_task = asyncio.create_task(self.upstream(), name="remote-dashboard-stream")

    async def close_sockets(self, app):
        for socket in tuple(app[BROWSER_SOCKETS]):
            await socket.close(code=1001)

    async def close_clients(self, app):
        if self.upstream_task:
            self.upstream_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.upstream_task
        if self.session:
            await self.session.close()


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=str(ROOT / ".dashboard.env"))
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("Invalid local port")
    try:
        origin, headers = configuration(args.env_file)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    logging.basicConfig(level=logging.INFO)
    dashboard = RemoteDashboard(origin, headers, args.port)
    # Do not echo remote origin, credentials, HTTP bodies or URLs in access logs.
    web.run_app(dashboard.app, host="127.0.0.1", port=args.port, access_log=None)
