# Local dashboard → hosted Meyaya

The existing dashboard stays on your Windows laptop. The laptop opens outbound
HTTPS/WSS connections to a separate, authenticated API on the hosted bot. It
does **not** connect to PostgreSQL, Redis, Discord or Gemini directly.

```text
Browser → http://127.0.0.1:8080 → laptop proxy (dashboard_remote.py)
                                      │ bearer + optional Access service credentials
                                      ▼ HTTPS / WSS
                               Cloudflare Access + named Tunnel
                                      │ outbound tunnel connector on HeavenCloud
                                      ▼ HTTP over host loopback only
                               127.0.0.1:8082 — Meyaya API
                                      │ existing services / shared clients
                               Discord, PostgreSQL, Redis, Gemini
```

There is no public dashboard HTML/login route in API mode. The tunnel goes on
**HeavenCloud**, not on the laptop. No callback URL is needed. Neither side needs
to connect inbound to your laptop. Existing hosted-dashboard and DB-direct local
dashboard launchers remain available as legacy alternatives, not this connection.

## What was reused

`bot/app.py` owns shared PostgreSQL/Redis/HTTP clients, cogs and background tasks.
The original aiohttp dashboard already provides server settings, usage,
memories, nicknames, blacklist controls, operational telemetry and error lookup.
The new API reuses those handlers, the existing `OwnerHealth`, telemetry and
model quota services. No database migration, extra database or provider test call
is required. Voice sessions and social games emit content-free lifecycle events.

## 1. Configure the connection

Generate a **new** random secret on your own terminal:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Store the same result privately on both ends. Do not use an existing bot/API key.
Do not post it in chat, pass it in a URL or commit it.

Exact added bot `.env.example` entries (example defaults, integration off):

```dotenv
DASHBOARD_ENABLED=false
DASHBOARD_MODE=hosted
DASHBOARD_API_TOKEN=
DASHBOARD_API_PORT=8082
DASHBOARD_API_ORIGIN=
DASHBOARD_ALLOW_MANAGEMENT=false
BOT_VERSION=unknown
CLOUDFLARED_EXECUTABLE=cloudflared
CLOUDFLARED_TOKEN_FILE=cloudflared-token.txt
```

For **HeavenCloud**, keep existing bot secrets there and set:

```dotenv
DASHBOARD_ENABLED=true
DASHBOARD_MODE=api
DASHBOARD_API_TOKEN=<new-random-secret>
DASHBOARD_API_PORT=8082
DASHBOARD_API_ORIGIN=https://meyaya-api.YOUR-DOMAIN
DASHBOARD_ALLOW_MANAGEMENT=false
BOT_VERSION=<deployed-commit-or-release>
CLOUDFLARED_EXECUTABLE=cloudflared
CLOUDFLARED_TOKEN_FILE=cloudflared-token.txt
```

API mode always binds `127.0.0.1`; it ignores the panel `PORT` allocation and
legacy dashboard bind/public URL settings. `DASHBOARD_ENABLED=false` disables
the integration. `DASHBOARD_MODE=hosted` preserves the old owner panel, which
uses its separate `DASHBOARD_TOKEN`. Do not tunnel that panel for this setup.

The laptop config is **separate**: copy `dashboard.env.example` to `.dashboard.env`:

```dotenv
MEYAYA_API_URL=https://meyaya-api.YOUR-DOMAIN
DASHBOARD_API_TOKEN=<same-new-random-secret>
CF_ACCESS_CLIENT_ID=<optional-service-token-client-id>
CF_ACCESS_CLIENT_SECRET=<optional-service-token-client-secret>
```

Do not copy the bot's `.env` to the laptop for this dashboard. No Discord,
database, Redis or Gemini credentials are needed by this launcher. Existing
environment variables override the separate file. Protect both private files
with owner-only filesystem permissions. `.dashboard.env` and the default tunnel
token filename are gitignored; custom filenames need their own ignore rule.

## 2. Cloudflare / HeavenCloud setup

**Not provisioned or verified against the live host yet.** Confirm HeavenCloud
permits running `cloudflared` beside the bot and outbound tunnel traffic before
changing the panel startup command. No public port allocation is needed.

1. Create a **named**, remotely managed Cloudflare Tunnel and stable hostname.
2. Route `meyaya-api.YOUR-DOMAIN` to `http://127.0.0.1:8082` on HeavenCloud.
   Leave the origin Host override unset so the original public hostname is
   preserved. Requests must arrive with `X-Forwarded-Proto: https`.
3. Recommended: create a self-hosted **Cloudflare Access application covering
   the whole hostname**, with a **Service Auth** policy accepting only your
   laptop's service token. Use the two credentials in `.dashboard.env`. An
   interactive browser-login policy is not suitable for the proxy's WebSocket.
4. Install a current `cloudflared` binary for the host OS/architecture through
   the provider's permitted process. Store the connector's tunnel token in
   `cloudflared-token.txt` privately, **not** in the API token variable. These
   are two unrelated credentials. Never put its contents in a command argument.
5. Verify the domain resolves and HTTPS certificate validation succeeds.

Official references:
[Tunnel tokens](https://developers.cloudflare.com/tunnel/reference/tunnel-tokens/),
[connector parameters and token-file support](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/run-parameters/),
[Access service tokens](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/),
[Tunnel setup/firewall requirements](https://developers.cloudflare.com/tunnel/get-started/).

HeavenCloud commands from the repository root:

```bash
python -m pip install --no-cache-dir --prefer-binary -r requirements.txt
python start.py --check
```

If the provider supports a separately supervised companion process:

```bash
cloudflared --no-autoupdate tunnel run --token-file cloudflared-token.txt
python start.py
```

These are **two separate long-running processes**, not consecutive foreground
commands in one terminal. If the panel only accepts one startup command, use:

```bash
python start_with_tunnel.py
```

The optional wrapper starts the existing bot launcher and connector as separate
processes, retries connector launches with backoff, and forwards shutdown by
terminating both children. Connector failure does not stop the bot. Connector
environment contains only allowlisted OS/runtime variables, not bot secrets.
stdout/stderr is suppressed to avoid credential leakage; check Cloudflare's
connector status for tunnel diagnosis. On Linux the bot receives SIGTERM and
uses its normal graceful shutdown. Windows child termination is best-effort.
Never run the wrapper and another bot instance simultaneously.

Firewall: allow the connector's required outbound TCP/UDP `7844`, plus existing
bot dependencies; laptop needs outbound HTTPS/WSS `443`. **Do not open inbound
8080/8082**, and do not create a tunnel to the laptop dashboard. A container must
run the connector in the same network namespace as the API or use a deliberately
configured private sidecar network; another container's loopback is different.

If HeavenCloud forbids companion binaries/outbound tunnel connectivity, this
Cloudflare deployment cannot work there. A provider-approved private networking
or HTTPS reverse proxy is then required; do not change the API bind to `0.0.0.0`
as a workaround. Tailscale needs provider support; ngrok is development only.
No actual provider/domain/tunnel account settings were changed by this work.

## 3. Start the laptop dashboard

In PowerShell:

```powershell
cd D:\Peoject\Meyaya
.\.venv-win\Scripts\Activate.ps1
Copy-Item dashboard.env.example .dashboard.env
# Edit .dashboard.env privately; populate only the four dashboard variables.
python dashboard_remote.py
```

Open `http://127.0.0.1:8080`. If another dashboard occupies 8080:

```powershell
python dashboard_remote.py --port 8081
```

Run the copy command only when first creating the file, not over an existing
configured file. You can supply `--env-file <private-path>`. The launcher uses
existing aiohttp/python-dotenv dependencies, not a new framework. It does not
start a Discord bot. `python dashboard.py` is the old DB-direct local mode.

## Authentication / security

- Every API and WS route requires constant-time `Authorization: Bearer …`
  comparison, including health. No token-in-query authentication or public
  liveness endpoint. A dedicated token must differ from existing bot/provider
  credentials. Remote API requests from browsers (Origin/Sec-Fetch-Site) fail.
- The origin listener accepts only loopback peers. With a configured API origin,
  it additionally checks the public Host and forwarded HTTPS marker. It trusts
  only the local connector, not arbitrary external proxy headers.
- One global bounded limit of 120 API/handshake attempts per minute, including
  invalid tokens; at most four upstream WS subscribers, each queue size 64.
- The laptop proxy accepts loopback peers/Host and same-origin browser traffic
  only. It holds credentials server-side and forwards only explicit routes.
  It never forwards browser Authorization headers or arbitrary target URLs.
  Redirects, including WS handshake redirects, are rejected. TLS verification
  remains enabled. No permissive CORS headers are added.
- Read-only by default. Enable `DASHBOARD_ALLOW_MANAGEMENT=true` deliberately
  to save server settings or blacklist changes; grants owner-level write access.
- Errors expose class/stage/ID rather than raw exceptions, SQL or credentials.
  A final recursive layer removes credential-bearing fields, known secrets,
  bearer strings and credential URLs. No event includes prompts/chat answers,
  game submissions or exception bodies. Snowflake IDs travel as strings.
- Existing explicit **owner** views for memory and recorded chat requests/answers
  remain accessible through authenticated REST, not broadcast through WS. Do
  not share the dashboard or its API token; it can read private owner records.
- No shell/eval/SQL/file/env operations, process restart or arbitrary cache
  deletion. Access logs are disabled on both listeners.
- Loopback protection does not authenticate other people/processes already on
  the laptop. Use an owner-only Windows account and private config permissions;
  a compromised/shared laptop can access the local dashboard. Cloudflare is a
  trusted TLS termination point. Rotate the dedicated token on both sides and
  restart the proxy/bot if it is exposed.

## Routes

All paths below are on the remote API; the laptop forwards the same allowlist.
`/api/connection` exists **only locally** and returns API/WS connectivity metadata.

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Full cached health, models, tasks, history, recent safe errors |
| GET | `/api/status` | Ready state, uptime, guild count, configured release |
| GET | `/api/guilds` | Server usage/settings, permissions, configured chat channel |
| GET | `/api/stats` | Existing bounded command and model aggregates |
| GET | `/api/commands/recent` | Latest 30 callbacks and timing groups |
| GET | `/api/errors/recent`, `/api/errors` | Safe errors; optional exact `?id=MY-XXXXXXXX` |
| GET | `/api/voice/status` | Discord voice connection/playing metadata |
| GET | `/api/games/status` | Active social-game count per guild |
| GET | `/api/cache/status` | Sizes, subscriber counts and dropped-event counter; no contents |
| GET | `/api/database/status`, `/api/redis/status` | Cached dependency result |
| GET | `/api/servers` | Existing server-selection UI report |
| GET | `/api/servers/{guild_id}/details` | Existing server/member detail view |
| GET | `/api/servers/{guild_id}/summary` | Existing server summary |
| GET | `/api/servers/{guild_id}/commands` | Persisted per-server command usage |
| GET | `/api/servers/{guild_id}/requests` | Explicit owner-request log view, including replies |
| GET | `/api/memories`, `/api/nicknames`, `/api/blacklist` | Existing owner records |
| GET | `/api/operations`, `/api/safety` | Existing operational and safety metadata |
| POST | `/api/guilds/{guild_id}/settings` | Same validator as existing PATCH server settings |
| PATCH | `/api/servers/{guild_id}` | Save exactly `{prefix, autoresponder, limit}` |
| PATCH | `/api/blacklist` | Existing validated blacklist operation |
| POST | `/api/control/reload` | Only `{"action":"guild_settings"}`; reload DB-backed settings |
| POST | `/api/cache/clear` | Only `{"scope":"dashboard"}`; clear dashboard caches, not global Redis |
| WS | `/ws/dashboard` | Authenticated remote stream; local browser stream via proxy |

POST/PATCH require JSON and the management flag. API handlers have a 10-second
deadline; laptop HTTP requests have a 12-second deadline and 5-second connect
timeout. Local responses are capped at 2 MiB. Unsupported routes fail closed.

## WebSocket events / recovery

Events: `bot.connected`, `bot.disconnected`, `bot.ready`, `bot.latency`,
`guild.joined`, `guild.left`, `command.started`, `command.completed`,
`command.failed`, `voice.joined`, `voice.left`, `voice.playback.started`,
`voice.playback.stopped`, `game.started`, `game.ended`, `error`,
`database.health`, `redis.health`, `rate_limit.warning`, `health.changed`.

Also protocol envelopes `snapshot`, `heartbeat`, and local-only `connection`.
Events carry type/timestamp/sequence and applicable IDs, command, duration,
status or safe error ID. Command events reflect callback execution, not argument
parsing/check failures. Voice playback events cover the song playback lifecycle;
voice status separately reports the continuous PCM stream, which may be silent.
Game lifecycle/status covers the existing social-game registry, **not every
court/solo game**. Warnings also include unsuccessful provider attempts, not
only HTTP 429. No event can trigger remote actions.

The laptop owns one upstream WS shared by up to eight browser tabs. WS pings run
every 15 seconds; remote JSON heartbeat runs on idle periods; the proxy considers
40 seconds without events stale. Reconnect uses exponential 1–30s backoff plus
jitter. Slow clients drop oldest queued events rather than blocking Discord.
Latest 100 events replay on connect; no durable delivery guarantee. Bot/laptop
restarts reset their local buffers. The browser reconnects locally and polls
API/health every 30 seconds when visible. Laptop sleeping/closing never prevents
Meyaya from handling Discord events.

Structured operational events log auth failures, API start/errors, WS lifecycle,
health changes and sample failures. The laptop logs WS reconnects without URLs,
headers or exception text. No permanent database writes are added for health.

## Health calculation / limits

Dependency probes share the bot's existing clients and pool, coalesce concurrent
readers and are cached for 30 seconds. Each DB/Redis probe has a 2-second deadline.
Samples every 15 seconds retain 120 points (~30 minutes) in memory; host CPU/RSS
and scheduler lag come from the existing minute sampler. Models use observed
outcomes and readonly quota snapshots, **not billable test generations**.

- **Unhealthy:** Discord not ready or a configured DB/Redis probe unavailable.
- **Degraded:** dependency latency >1000ms; a tracked worker stopped; provider
  degraded/unavailable; loop lag >250ms; RSS ≥85% of container memory limit;
  throttle ratio ≥10%; process CPU ≥45% of one core (near the 0.5-core plan);
  host sample older than 150 seconds; >10% callback failures with ≥10 recent
  callbacks; or a Discord/AI voice session not ready.
- **Healthy:** none of those observed conditions. Missing model observations
  remain **Unknown**, not proof of Google availability. Optional disabled Redis
  is marked Disabled, not automatically an error.

CPU is process CPU time / wall time, **percentage of one core**, not total host
utilization. Throttle ratio is separate. RSS excludes the connector/other
processes; cgroup memory limit is the container budget. Monitor HeavenCloud's
whole-container usage too: `cloudflared` adds CPU/RAM. Unsupported Linux files
and Windows memory readings stay Unknown, never fabricated zeros.
Counts/last-hour error rate are process-local and bounded to the latest 2,000
callbacks; not a complete long-term audit. Users seen is capped at 10,000;
Discord member counts are whatever the legitimate gateway cache provides.
The two main bot background tasks and voice watcher are tracked, not arbitrary
third-party tasks. Health graph scales are independent and missing points are
omitted. Exactly matching configured secrets is defense in depth, not a promise
to detect every possible unconfigured credential pasted into a private record.

## Tests / deployment verification

Offline integration tests (no real token/DB/Google/Discord calls):

```powershell
python -m unittest -v test_dashboard_connection
python -m pytest -q
```

Tests cover missing/wrong auth, Origin/transport/rate checks, no public HTML,
dependency/Discord outages, secret redaction, write allowlists, WS auth/broadcast,
repeated browser connections, upstream stream reconnect, unavailable bot,
bounded queues, and no API token in browser HTML/JS. Existing tests cover
disabled dashboard startup and bot services. The standalone test is tracked
even though the repository's old `tests/` directory is ignored.

After configuring the real tunnel:

1. Open the laptop dashboard; verify API/WS connected, release and health.
2. Run an ordinary Discord command; check live timing and server usage.
3. Enter a reported `MY-XXXXXXXX` error ID; verify only safe diagnostic metadata.
4. Close/reopen the laptop dashboard and sleep/wake the laptop: bot stays online.
5. Restart the hosted bot: laptop reconnects without refreshing credentials.
6. Stop the connector: API goes unavailable, stream reconnects, bot keeps working.
7. Test an incorrect dashboard token locally: 401; restore it privately.
8. In an isolated dev setup, disconnect DB/Redis: health must turn unhealthy.
9. Confirm unauthorized browser requests to the public hostname are blocked by
   Access; do not expose 8082 or dashboard HTML publicly.

Do not deliberately interrupt production DB/Redis to test health. Live tunnel,
HeavenCloud deployment, real voice/game operation and browser visual checks are
separate verification steps; offline tests cannot prove them.

## Files in this implementation

Created: `bot/web/management.py` (API/auth/allowlist/health/WS),
`bot/web/remote.py` (local proxy/config/reconnect), `bot/web/dashboard_events.py`
(bounded content-free fan-out), `bot/web/dashboard_sanitizer.py` (redaction),
`dashboard_remote.py` (Windows launcher), `start_with_tunnel.py` (optional host
companion launcher), `dashboard.env.example`, `test_dashboard_connection.py`,
and this guide.

Modified: `bot/config/settings.py`, `bot/app.py`, `start.py`,
`bot/cogs/admin.py` (owner command gives local-launch instructions in API mode),
`bot/web/dashboard.py`, `bot/web/index.html`, `bot/web/dashboard.js`,
`bot/logging/telemetry.py`, `bot/utils/command_timing.py`,
`bot/utils/host_metrics.py`, `bot/services/voice_session.py`, `.env.example`,
`.gitignore`, `README.md`; existing ignored `tests/test_resilience_timing.py`
was adjusted to check both start and completion telemetry. Earlier uncommitted
owner-health/GIF/card changes remain preserved and are separate from this work.

Remaining deployment requirements: your Cloudflare account/domain/service token,
connector binary/token, and provider permission for a companion process. No
domain or tunnel was created and no secrets/changes were pushed or deployed.
