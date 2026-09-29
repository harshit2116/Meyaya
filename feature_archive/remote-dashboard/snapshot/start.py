"""HeavenCloud/Pterodactyl entry point: python start.py (Python 3.12)."""

import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def prepare_environment():
    # Panel secrets win over .env; defaults must not override either.
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    defaults = {
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "MALLOC_ARENA_MAX": "2",
        "AI_MAX_CONCURRENT": "1",
        "AI_USER_COOLDOWN_SECONDS": "5",
        "DISCORD_MESSAGE_CACHE_SIZE": "25",
        "DISCORD_CHUNK_ON_STARTUP": "false",
        "VOICE_MAX_SESSIONS": "1",
        "REDIS_REQUIRED": "true",
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate configuration without connecting")
    parser.add_argument("--skip-migrations", action="store_true", help="Only if migrations were run separately")
    args = parser.parse_args()
    os.chdir(ROOT)
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("Select the Python 3.12 runtime in the hosting panel.")
    prepare_environment()
    from bot.config.settings import Settings
    from pydantic import ValidationError

    try:
        settings = Settings()
    except ValidationError as error:
        # Pydantic's full error can include tokens or credential-bearing URLs.
        fields = sorted({str(item["loc"][0]) for item in error.errors()})
        raise SystemExit("Missing or invalid configuration: " + ", ".join(fields)) from None
    if not settings.discord_token.strip() or not settings.database_url.strip() or not settings.redis_url.strip():
        raise SystemExit("Set DISCORD_TOKEN, DATABASE_URL and REDIS_URL in the panel or .env.")
    if settings.dashboard_enabled:
        credential = settings.dashboard_api_token if settings.dashboard_mode == 'api' else settings.dashboard_token
        if len(credential) < 32:
            raise SystemExit("Configure the selected dashboard mode with a separate random token of at least 32 characters.")
    print("Configuration valid. Use external PostgreSQL/Redis and one bot process.", flush=True)
    if args.check:
        print("Offline check only: database, Redis, Discord and voice connectivity were not tested.")
        return
    if not args.skip_migrations:
        # Separate process exits before Discord/Pillow/voice are loaded, reducing peak RAM.
        result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT)
        if result.returncode:
            raise SystemExit("Database migration failed; bot was not started.")
    if sys.platform == "win32":
        # Windows execv does not preserve the shell's wait on this process.
        # Run in-process so PowerShell stays attached and Ctrl+C reaches asyncio.
        from bot.main import run

        run()
    else:
        # On Linux hosting, replace the launcher so SIGTERM reaches the bot and
        # no parent process stays resident.
        os.execv(sys.executable, [sys.executable, "-m", "bot.main"])


if __name__ == "__main__":
    main()
