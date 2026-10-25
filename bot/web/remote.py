"""Loopback-only bridge to the running bot. Credentials never reach JavaScript."""
import re
from types import SimpleNamespace
from urllib.parse import urlsplit

from aiohttp import ClientSession, ClientTimeout, ClientError, web
from bot.web.dashboard import Dashboard
from bot.web.local import LocalDashboard


class RemoteDashboard(LocalDashboard):
    def __init__(self, settings):
        origin = settings.dashboard_remote_url.rstrip('/')
        parsed = urlsplit(origin)
        tunnel = bool((getattr(settings, 'dashboard_ssh_host', '') or
                       getattr(settings, 'dashboard_ssm_instance', '')) and
                      parsed.scheme == 'http' and parsed.hostname == '127.0.0.1')
        if ((parsed.scheme != 'https' and not tunnel) or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment):
            raise ValueError('Use a plain HTTPS origin, or loopback HTTP with a configured SSH tunnel')
        if len(settings.dashboard_api_token) < 32:
            raise ValueError('Set DASHBOARD_API_TOKEN to the AWS read-only API token')
        Dashboard.__init__(self, SimpleNamespace(settings=settings), local_no_auth=True)
        self._client = None

        @web.middleware
        async def bridge(request, handler):
            if not request.path.startswith('/api/'):
                return await handler(request)
            editing = request.method == 'PATCH' and re.fullmatch(r'/api/servers/[0-9]+', request.path)
            edit_token = getattr(settings, 'dashboard_remote_edit_token', '')
            if request.method not in {'GET', 'HEAD'} and not (editing and edit_token):
                raise web.HTTPForbidden(text='Editing is not enabled for this console')
            try:
                options = {'allow_redirects': False}
                method = self._client.get
                if editing:
                    method = self._client.patch
                    options.update(json=await request.json(), headers={'Authorization': f'Bearer {edit_token}'})
                async with method(origin + request.rel_url.path_qs, **options) as response:
                    if response.status == 401:
                        raise web.HTTPBadGateway(text='AWS rejected the dashboard API token. Check the token on both machines.')
                    if response.status != 200:
                        raise web.HTTPBadGateway(text=f'AWS dashboard returned HTTP {response.status}.')
                    data = await response.json()
                    if request.path == '/api/servers':
                        data['mode'] = 'remote'
                        data['can_edit'] = bool(edit_token)
                    return web.json_response(data)
            except (ClientError, TimeoutError, ValueError):
                raise web.HTTPBadGateway(text='Cannot reach the AWS dashboard. Check its HTTPS address and service status.') from None

        self.app.middlewares.append(bridge)

        async def client_context(app):
            async with ClientSession(timeout=ClientTimeout(total=15),
                    headers={'Authorization': f'Bearer {settings.dashboard_api_token}'}) as client:
                self._client = client
                yield
        self.app.cleanup_ctx.append(client_context)
