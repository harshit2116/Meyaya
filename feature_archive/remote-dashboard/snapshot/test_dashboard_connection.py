"""Offline integration checks: python -m unittest -v test_dashboard_connection."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from aiohttp import web, WSServerHandshakeError
from aiohttp.test_utils import TestClient, TestServer
from bot.logging.health import health
from bot.web.dashboard_events import EventHub, hub
from bot.web.dashboard_sanitizer import sanitize
from bot.web.management import ManagementAPI
from bot.web.remote import RemoteDashboard, configuration

TOKEN = "independent-dashboard-secret-" + "x" * 32


def bot_fixture():
    session = SimpleNamespace(execute=AsyncMock())

    @asynccontextmanager
    async def factory():
        yield session

    bot = SimpleNamespace(
        settings=SimpleNamespace(
            dashboard_token="",
            dashboard_api_token=TOKEN,
            dashboard_api_origin="",
            dashboard_api_port=8082,
            dashboard_allow_management=False,
            bot_version="test-release",
            ai_enabled=False,
            gemini_api_key="private-gemini-key",
            discord_token="private-discord-token",
            database_url="postgresql://u:private-password@db/test",
            redis_url="redis://:redis-password@cache",
            dashboard_host="127.0.0.1",
            dashboard_public_url="",
            gemini_live_model="test-live",
        ),
        guilds=[],
        users=[],
        voice_clients=[],
        latency=0.042,
        is_ready=lambda: True,
        get_cog=lambda name: None,
        session_factory=factory,
        redis=SimpleNamespace(ping=AsyncMock()),
        _dashboard_settings_refresh=None,
        _request_log_maintenance=None,
    )
    return bot, session


class ConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot, self.database = bot_fixture()
        self.api = ManagementAPI(self.bot)
        self.server = TestServer(self.api.app)
        self.client = TestClient(self.server)
        await self.client.start_server()
        self.auth = {"Authorization": "Bearer " + TOKEN}

    async def asyncTearDown(self):
        await self.api.close()
        await self.client.close()

    async def test_authentication_all_routes_and_no_panel(self):
        for route in (
            "/api/health",
            "/api/status",
            "/api/guilds",
            "/ws/dashboard",
            "/api/control/reload",
        ):
            response = await self.client.get(route)
            self.assertEqual(response.status, 401)
        response = await self.client.get("/api/status", headers={"Authorization": "Bearer wrong"})
        self.assertEqual(response.status, 401)
        response = await self.client.get("/", headers=self.auth)
        self.assertEqual(response.status, 404)
        response = await self.client.get("/api/status", headers=self.auth)
        self.assertEqual((await response.json())["version"], "test-release")

    async def test_readonly_route_catalog(self):
        self.bot.usage = SimpleNamespace(report=AsyncMock(return_value=({}, {})))
        for path in ('/api/health', '/api/status', '/api/guilds', '/api/stats',
                     '/api/commands/recent', '/api/errors/recent', '/api/voice/status',
                     '/api/games/status', '/api/cache/status', '/api/database/status',
                     '/api/redis/status'):
            response = await self.client.get(path, headers=self.auth)
            self.assertEqual(response.status, 200, path)
            self.assertNotIn('private-discord-token', await response.text())

    async def test_connector_does_not_inherit_bot_credentials(self):
        from start_with_tunnel import connector_environment
        with patch.dict('os.environ', {'DISCORD_TOKEN': 'private', 'GEMINI_API_KEY': 'private',
                                       'DASHBOARD_API_TOKEN': TOKEN, 'DATABASE_URL': 'private',
                                       'PATH': 'safe-runtime-path'}):
            env = connector_environment()
            self.assertEqual(env['PATH'], 'safe-runtime-path')
            self.assertNotIn('DISCORD_TOKEN', env)
            self.assertNotIn('DASHBOARD_API_TOKEN', env)
            self.assertNotIn('GEMINI_API_KEY', env)
            self.assertNotIn('DATABASE_URL', env)

    async def test_cross_origin_rate_limit_and_transport(self):
        response = await self.client.get(
            "/api/status", headers={**self.auth, "Origin": "https://evil.example"}
        )
        self.assertEqual(response.status, 403)
        self.api.origin = "https://api.example.com"
        response = await self.client.get("/api/status", headers=self.auth)
        self.assertEqual(response.status, 403)
        response = await self.client.get(
            "/api/status",
            headers={**self.auth, "Host": "api.example.com", "X-Forwarded-Proto": "https"},
        )
        self.assertEqual(response.status, 200)
        self.api.origin = ""
        for _ in range(120):
            self.api.rate.append(asyncio.get_running_loop().time())
        response = await self.client.get("/api/status", headers=self.auth)
        self.assertEqual(response.status, 429)

    async def test_health_dependency_failures_and_redaction(self):
        response = await self.client.get("/api/health", headers=self.auth)
        data = await response.json()
        self.assertEqual(response.status, 200)
        self.assertEqual(data["dependencies"][0]["latency_ms"], 42)
        self.database.execute.side_effect = RuntimeError("private-password")
        self.bot.redis.ping.side_effect = RuntimeError("redis-password")
        self.bot.is_ready = lambda: False
        self.api.owner_health.cache = None
        response = await self.client.get("/api/health", headers=self.auth)
        data = await response.json()
        self.assertEqual(data["status"], "unhealthy")
        self.assertEqual([row["status"] for row in data["dependencies"]], ["unavailable"] * 3)
        self.assertNotIn("password", json.dumps(data))
        self.assertNotIn("private-gemini-key", json.dumps(data))
        self.assertEqual(
            sanitize({"token": TOKEN, "text": "Bearer " + TOKEN}, (TOKEN,)),
            {"text": "Bearer [redacted]"},
        )

    async def test_management_allowlist(self):
        response = await self.client.post(
            "/api/cache/clear", headers=self.auth, json={"scope": "dashboard"}
        )
        self.assertEqual(response.status, 403)
        self.bot.settings.dashboard_allow_management = True
        response = await self.client.post(
            "/api/cache/clear", headers=self.auth, json={"scope": "all"}
        )
        self.assertEqual(response.status, 400)
        response = await self.client.post(
            "/api/cache/clear", headers=self.auth, json={"scope": "dashboard"}
        )
        self.assertEqual(response.status, 200)

    async def test_websocket_auth_broadcast_and_client_restart(self):
        with self.assertRaises(WSServerHandshakeError):
            await self.client.ws_connect("/ws/dashboard")
        for _ in range(2):
            async with self.client.ws_connect("/ws/dashboard", headers=self.auth) as socket:
                snapshot = await socket.receive_json(timeout=2)
                self.assertEqual(snapshot["type"], "snapshot")
                hub.publish(
                    {
                        "event": "command_timing",
                        "status": "success",
                        "command": "profile",
                        "guild_id": 715925710849572904,
                        "total_ms": 50,
                        "content": "private-message",
                    }
                )
                data = await socket.receive_json(timeout=2)
                self.assertEqual(data["type"], "command.completed")
                self.assertEqual(data["guild_id"], "715925710849572904")
                self.assertNotIn("private-message", json.dumps(data))

    async def test_laptop_proxy_no_secret_to_browser_and_unavailable_bot(self):
        origin = str(self.server.make_url("")).rstrip("/")
        proxy = RemoteDashboard(origin, self.auth)
        async with TestClient(TestServer(proxy.app)) as laptop:
            response = await laptop.get("/")
            html = await response.text()
            self.assertNotIn(TOKEN, html)
            self.assertIn('data-remote-dashboard="true"', html)
            response = await laptop.get("/dashboard.js")
            self.assertNotIn(TOKEN, await response.text())
            response = await laptop.get("/api/status")
            self.assertEqual(response.status, 200)
            response = await laptop.get("/api/status", headers={"Origin": "https://evil.example"})
            self.assertEqual(response.status, 403)
            response = await laptop.get("/api/not-allowed")
            self.assertEqual(response.status, 404)
            proxy.origin = "http://127.0.0.1:1"
            response = await laptop.get("/api/status")
            self.assertEqual(response.status, 503)
        # Closing the laptop does not change the bot's readiness or health services.
        self.assertTrue(self.bot.is_ready())

    async def test_bot_websocket_restart_reconnects(self):
        connections = 0

        async def stream(request):
            nonlocal connections
            connections += 1
            socket = web.WebSocketResponse()
            await socket.prepare(request)
            await socket.send_json(
                {"type": "bot.ready", "timestamp": datetime.now(UTC).isoformat()}
            )
            await socket.close()
            return socket

        app = web.Application()
        app.router.add_get("/ws/dashboard", stream)
        async with TestServer(app) as upstream:
            proxy = RemoteDashboard(str(upstream.make_url("")).rstrip("/"), self.auth)
            async with TestClient(TestServer(proxy.app)):
                async with asyncio.timeout(5):
                    while connections < 2:
                        await asyncio.sleep(0.05)
                self.assertGreaterEqual(connections, 2)
                self.assertTrue(proxy.events)

    async def test_bounded_fanout_and_safe_configuration(self):
        events = EventHub()
        queue = events.subscribe()
        for i in range(200):
            events.publish({"event": "command.started", "command": "help", "body": TOKEN})
        self.assertEqual(len(events.history), 100)
        self.assertEqual(queue.qsize(), 64)
        self.assertGreater(events.dropped, 0)
        self.assertNotIn(TOKEN, json.dumps(list(events.history)))
        with patch.dict(
            "os.environ", {"MEYAYA_API_URL": "http://public.example", "DASHBOARD_API_TOKEN": TOKEN}
        ):
            with self.assertRaises(ValueError):
                configuration("missing-file")

    async def test_redirect_does_not_forward_secrets(self):
        received = []

        async def destination(request):
            received.append(dict(request.headers))
            return web.json_response({"unexpected": True})

        app = web.Application()
        app.router.add_get("/ws/dashboard", destination)
        async with TestServer(app) as target:

            async def redirect(request):
                raise web.HTTPFound(location=str(target.make_url("/ws/dashboard")))

            source = web.Application()
            source.router.add_get("/ws/dashboard", redirect)
            async with TestServer(source) as upstream:
                proxy = RemoteDashboard(
                    str(upstream.make_url("")).rstrip("/"),
                    {**self.auth, "CF-Access-Client-Secret": "private-access-secret"},
                )
                async with TestClient(TestServer(proxy.app)):
                    await asyncio.sleep(0.2)
                    self.assertEqual(received, [])

    async def test_disabled_mode_and_separate_credential(self):
        from bot.config.settings import Settings

        settings = Settings(
            DISCORD_TOKEN="test",
            DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
            REDIS_URL="redis://localhost",
            DASHBOARD_ENABLED=False,
            _env_file=None,
        )
        self.assertFalse(settings.dashboard_enabled)
        self.assertEqual(settings.dashboard_api_token, "")
        self.bot.settings.discord_token = TOKEN
        with self.assertRaises(ValueError):
            ManagementAPI(self.bot)


if __name__ == "__main__":
    unittest.main()
