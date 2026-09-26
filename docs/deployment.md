# Running Meyaya

For the 512 MB HeavenCloud bot-hosting panel, use [this guide](heavencloud.md) instead of Compose.
The Compose example below requires additional RAM for PostgreSQL and Redis outside the bot's 512 MB limit.

## Local Redis repair

Start Docker Desktop, then run:

```powershell
docker compose up -d redis
docker compose exec redis redis-cli ping
```

The reply should be `PONG`. Keep `REDIS_URL=redis://localhost:6379/0` in the local `.env`.
Only Redis starts without the deployment profile. It listens on localhost, saves data in a named
volume using append-only persistence, and restarts with Docker. Never use `down -v` unless you
intend to delete persisted data. Redis memory is capped at 256 MB with no eviction so saved
monitor settings cannot silently disappear; inspect storage and memory as the server grows.

Redis calls use two-second connection/command timeouts and a bounded connection pool. Local mode
can run with reduced functionality during an outage. `REDIS_REQUIRED=true` makes startup fail
clearly if Redis is unavailable. Subsequent requests reconnect automatically when it recovers.

## Deployment with Docker Compose

This is a single-process deployment. Active games and some cooldowns remain in memory, so finish
games before restarting. Do not scale multiple bot instances with the same Discord token.

1. Copy `.env.example` to `.env` on the deployment host and set the API keys and Discord token.
2. Add `POSTGRES_PASSWORD` with a strong password and set
   `DEPLOY_DATABASE_URL=postgresql+asyncpg://meyaya:YOUR_URL_ENCODED_PASSWORD@postgres:5432/meyaya`.
   Both passwords must match; URL-encode reserved characters in the database URL only.
3. Securely copy any private identity/rule files to the host. Only the sanitized personality
   JSON and persona reference are public and included in images/packages; other private files
   remain excluded. If mounting `bot/private/` read-only, include the two public files too so the
   mount does not hide them. Ensure the container user (UID 10001) can read it. Leave `GUILD_ID` empty for
   global slash-command registration.
4. Back up your existing PostgreSQL and Redis data. The new Compose database starts empty;
   it does not import your Windows database. Restore your database backup before starting the bot
   if you want to keep relationships, memories, and settings.
5. Build and start:

```sh
docker compose --profile deployment build
docker compose --profile deployment up -d
docker compose logs --tail 100 bot
```

Compose waits for PostgreSQL health, runs Alembic migrations, and starts the bot only after the
migration succeeds and Redis is healthy. PostgreSQL is not exposed to the host network. Redis is
bound only to localhost. No inbound bot ports are needed; the host needs outbound HTTPS and UDP
for Discord voice. The bot runs as an unprivileged user with Python 3.12 and native voice libraries.

For updates, back up the database, rebuild, then run the `up` command above. Check `/status` and
exercise one chat message and voice session. Bot logs have a named volume; Docker console logs
should also be rotated by the Docker daemon. Keep `.env`, private files, database dumps, and
Redis backups out of Git. Retain backups off the deployment host and practice restoring them.

## Verification and limits

```sh
python -m pytest -q
alembic check
docker compose --profile deployment config --quiet
```

Do not print the rendered Compose configuration without `--quiet`: it contains environment secrets.
Dependency versions currently use minimum constraints, except the pinned voice receiver commit.
Before release, build and verify the image, then deploy that same image digest; rebuilding later
can resolve newer dependencies. Live Discord and Gemini checks require the configured accounts.

The Redis options follow [Redis production guidance](https://redis.io/docs/latest/develop/clients/redis-py/produsage/).
Service ordering follows [Compose health checks](https://docs.docker.com/compose/how-tos/startup-order/).
