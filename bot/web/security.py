"""Fail-closed dashboard transport checks and short-lived owner sessions."""

from collections import deque
from hashlib import sha256
from ipaddress import ip_address, ip_network
import secrets
import time
from urllib.parse import urlsplit

from aiohttp import web

SESSION_SECONDS = 3600
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class DashboardSecurity:
    def __init__(self, settings):
        self.settings = settings
        self.sessions = {}
        self.attempts = {}

    def origin(self):
        value = getattr(self.settings, "dashboard_public_url", "").strip()
        if not value:
            return None
        parsed = urlsplit(value)
        if (not parsed.hostname or parsed.username or parsed.password or parsed.query
                or parsed.fragment or parsed.path not in {"", "/"}):
            raise ValueError("DASHBOARD_PUBLIC_URL must be a plain dashboard origin")
        _ = parsed.port  # Reject invalid ports before binding a listener.
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in LOCAL_HOSTS):
            raise ValueError("Remote dashboard access requires HTTPS")
        return parsed

    def proxies(self):
        networks = []
        for value in getattr(self.settings, "dashboard_trusted_proxies", "").split(","):
            if value.strip():
                network = ip_network(value.strip(), strict=False)
                if network.prefixlen == 0:
                    raise ValueError("Trust specific proxy addresses, not the entire Internet")
                networks.append(network)
        return networks

    def validate_config(self):
        origin = self.origin()
        remote = origin is not None and origin.hostname not in LOCAL_HOSTS
        if remote and not self.proxies():
            raise ValueError("Set DASHBOARD_TRUSTED_PROXIES to the HTTPS reverse proxy's IP or CIDR")
        if not remote and getattr(self.settings, "dashboard_host", "127.0.0.1") not in LOCAL_HOSTS:
            raise ValueError("A non-loopback dashboard listener requires an HTTPS public URL and trusted proxy")

    def check_request(self, request):
        self.validate_config()
        origin = self.origin()
        remote = origin is not None and origin.hostname not in LOCAL_HOSTS
        try:
            peer = ip_address(request.remote or "")
            host = urlsplit("//" + request.host)
            if remote:
                if not any(peer in network for network in self.proxies()):
                    raise ValueError()
                # The configured proxy must overwrite this header and preserve Host.
                if request.headers.get("X-Forwarded-Proto", "").lower() != "https":
                    raise ValueError()
                if request.host.lower() != origin.netloc.lower():
                    raise ValueError()
                expected_origin = origin.geturl().rstrip("/")
            else:
                if not peer.is_loopback or host.hostname not in LOCAL_HOSTS:
                    raise ValueError()
                expected_origin = f"http://{request.host}"
            supplied_origin = request.headers.get("Origin")
            if supplied_origin and supplied_origin != expected_origin:
                raise ValueError()
            if request.headers.get("Sec-Fetch-Site") == "cross-site":
                raise ValueError()
        except ValueError:
            raise web.HTTPForbidden(text="Dashboard origin or secure transport rejected") from None

    def throttle(self, peer):
        now = time.monotonic()
        self.attempts = {key: events for key, events in self.attempts.items() if events and now - events[-1] < 60}
        if peer not in self.attempts and len(self.attempts) >= 256:
            raise web.HTTPTooManyRequests(headers={"Retry-After": "60"})
        events = self.attempts.setdefault(peer, deque())
        while events and now - events[0] >= 60:
            events.popleft()
        if len(events) >= 20:
            raise web.HTTPTooManyRequests(text="Too many login attempts", headers={"Retry-After": "60"})
        events.append(now)

    def issue_session(self):
        now = time.monotonic()
        self.sessions = {key: expiry for key, expiry in self.sessions.items() if expiry > now}
        if len(self.sessions) >= 8:
            self.sessions.pop(next(iter(self.sessions)))
        token = secrets.token_urlsafe(32)
        self.sessions[sha256(token.encode()).hexdigest()] = now + SESSION_SECONDS
        return token

    def authenticated(self, token):
        key = sha256(token.encode()).hexdigest()
        expiry = self.sessions.get(key, 0)
        if expiry <= time.monotonic():
            self.sessions.pop(key, None)
            return False
        return True

    def revoke(self, token):
        self.sessions.pop(sha256(token.encode()).hexdigest(), None)
