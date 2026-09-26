# HeavenCloud: 512 MB setup

HeavenCloud's [bot hosting](https://heavencloud.in/service/bot-hosting) uses a Pterodactyl panel, not a VPS. This setup runs **one Python bot process**. PostgreSQL and Redis must be external services, not extra processes inside the 512 MB allocation. A 512 MB target is not a tested guarantee for every guild count or concurrent voice/card workload.

## 1. Runtime and upload

### Deploy from GitHub

Use `https://github.com/harshit2116/Meyaya` and branch `main` in the panel's Git Repo Address and Git Branch fields. Select Python 3.12 and set App py file to `start.py`. Keep Auto Update disabled until an update is intentionally deployed. A repository URL alone may only be cloned during installation; do not reinstall an existing server with files without backing it up first.

The repository contains application code, migrations, artwork, dashboard files, dependency declarations, and the public personality config. It deliberately excludes `.env`, private identity/roleplay overrides, virtual environments, tests, logs, and deployment archives. GitHub is not a secret store: configure credentials privately in HeavenCloud before starting. Private prompt overrides are optional; built-in defaults are used when absent. To preserve local overrides, supply them separately using `MEYAYA_PRIVATE_CONFIG_JSON` or private files.

- Select Python **3.12**. Set the startup file to `start.py` (or startup command to `python -u start.py`). Panel labels vary; ask support if this is locked.
- The image needs Git for the pinned voice receiver dependency, `libopus0`/`libsodium`, and DejaVu fonts for the card layouts. Ask support for an image with these installed; bot containers generally cannot use sudo. FFmpeg is only needed for paths that decode audio; public singing is archived.
- Upload/clone the source with `bot/`, its assets/data, `alembic/`, `alembic.ini`, `pyproject.toml`, `README.md`, `requirements.txt`, and `start.py`.
- Do not upload `.venv*`, `.git`, tests, tools, logs, caches, database dumps, or your Windows FFmpeg executable.
- Upload `bot/private/` separately through the secure panel file manager, or use the supported `MEYAYA_PRIVATE_CONFIG_JSON` secret. Never put it in Git.
- Install once, not on every restart: `python -m pip install --no-cache-dir -r requirements.txt`. Do not install `.[dev]`. The requirements file uses the existing pyproject dependency list. Versions still use minimum bounds; save the resolved versions after a successful installation for repeatable updates.

## 2. Environment

Use panel secrets, or copy `.env.example` to `.env` securely. Keep API keys and model IDs from your working configuration. Change these values explicitly if copying the example:

```dotenv
DATABASE_URL=postgresql+asyncpg://USER:URL_ENCODED_PASSWORD@EXTERNAL_HOST:5432/DB?sslmode=require
REDIS_URL=rediss://default:URL_ENCODED_PASSWORD@EXTERNAL_HOST:6379/0
REDIS_REQUIRED=true
REDIS_TLS_VERIFY=true
AI_MAX_CONCURRENT=1
AI_USER_COOLDOWN_SECONDS=5
DISCORD_MESSAGE_CACHE_SIZE=25
DISCORD_CHUNK_ON_STARTUP=false
VOICE_MAX_SESSIONS=1
VOICE_SESSION_MINUTES=10
GUILD_ID=
FFMPEG_EXECUTABLE=ffmpeg
PYTHONUNBUFFERED=1
PYTHONDONTWRITEBYTECODE=1
MALLOC_ARENA_MAX=2
```

Use the external providers' exact URLs/ports and TLS requirements, not the placeholders above. Set `DISCORD_TOKEN`, `GEMINI_API_KEY`, and other API keys separately. Keep Message Content and Server Members intents enabled in the Discord portal. Do not copy localhost database URLs from Windows.

The launcher supplies low-memory defaults only when a value is absent; panel variables override `.env`. Disabling startup member chunking avoids downloading every guild member at login, but member-cache-based lists may initially be incomplete. Discord events and command lookups populate members as needed; this is not a hard cap on member-cache memory. Message history cache is reduced to 25; older cached-message event handling may be unavailable. The original server quota and exemption remain unchanged.

## 3. First launch and existing data

### Upstash Redis

Meyaya's selected database is `Meyayay`, in Mumbai (`ap-south-1`), on the free plan. It uses the endpoint `warm-grubworm-299105.upstash.io:6379`. TLS is enabled; eviction and automatic paid upgrades are disabled.

Use its **TCP password/connection string** in the private environment:

```dotenv
REDIS_URL=rediss://default:URL_ENCODED_PASSWORD@warm-grubworm-299105.upstash.io:6379/0
REDIS_REQUIRED=true
REDIS_TLS_VERIFY=true
```

The REST endpoint/token variables are not used by Meyaya's `redis.asyncio` client. Copy the same private settings into HeavenCloud's environment or secure `.env` upload. The host needs outbound TCP access to port 6379. Run `python -m bot.check_redis` on HeavenCloud before launching; it verifies authentication, transactions, reads/writes and expiry with a disposable probe key. It never prints the password. A local successful check does not verify the host's network access.

The free database currently allows 500,000 commands per month. Monitor consumption in Upstash: a single bot message can execute several Redis commands. Reaching the free allowance will affect Redis-backed features. New databases start empty; changing REDIS_URL does not migrate old chat history or Redis-backed monitor settings.

Stop the Windows bot before starting the hosted copy. Back up PostgreSQL and Redis first. If moving to new services, restore those backups before launching; migrations do not transfer memories, relationships or settings.

Run `python start.py --check` for an offline configuration check. Then start normally. `start.py` runs `alembic upgrade head` in a separate process and starts the bot only on success. Migrations run on each boot and are no-ops when current. Use `--skip-migrations` only when you already migrated separately. Do not run two replicas against the same token.

## 4. Dashboard

Leave the dashboard disabled until the host supplies an HTTPS reverse proxy and an allocated web port. Then set:

```dotenv
DASHBOARD_ENABLED=true
DASHBOARD_HOST=0.0.0.0
DASHBOARD_PORT=YOUR_ALLOCATED_PORT
DASHBOARD_PUBLIC_URL=https://YOUR_DASHBOARD_DOMAIN
DASHBOARD_TRUSTED_PROXIES=YOUR_PROXY_IP_OR_PRIVATE_CIDR
DASHBOARD_TOKEN=YOUR_RANDOM_SECRET_AT_LEAST_32_CHARACTERS
```

`PORT`, if supplied, overrides `DASHBOARD_PORT`; confirm it matches the proxy allocation. Generate the token locally with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Never expose authenticated dashboard traffic over plain HTTP. Ask HeavenCloud support about proxy/port availability and the proxy's source IP for your plan. The proxy must preserve the public Host header, overwrite `X-Forwarded-Proto` with `https`, and be the only source allowed to reach the backend port. Configure only its actual IP or narrow private CIDR, never the whole Internet. Without these settings, remote dashboard access is refused. `uwu owner` privately sends your login link after configuration. Browser sessions expire after one hour and are revoked by Lock dashboard; the permanent token is never returned by the login API.

## 5. Verify the 512 MB target

Watch **container memory in the panel**, not only Python RSS. Test login, chat, two users requesting cards, profile/duostyle, dashboard browsing, and one voice session with multiple speakers. Check the render queue and clean provider-error response. Leave headroom below 512 MB; sustained usage above roughly 400 MB calls for fewer simultaneous workloads or a larger plan. No live HeavenCloud load test has been performed here.

Image rendering already has one worker and a bounded queue/cache; the database pool has two connections plus one overflow. The new launcher limits concurrent text work to one by default. Voice remains available with one session, but mixed voice/card workloads need testing. Do not add workers to speed things up on this plan. Logs rotate locally; keep backups externally and monitor the plan's disk allowance. For updates, back up, stop, replace source/install dependencies, and start again.
