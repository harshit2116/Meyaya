"""Optional HeavenCloud launcher for a bot plus a loopback Cloudflare connector.

The connector is a separate process: its failure never stops Meyaya. Requires
an installed cloudflared binary and a privately stored named-tunnel token file.
"""

import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent


def connector_environment():
    # The connector needs OS/runtime configuration, not the bot's credentials.
    allowed = {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'HOME', 'USERPROFILE',
               'LANG', 'LC_ALL', 'SSL_CERT_FILE', 'SSL_CERT_DIR'}
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


def main():
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    enabled = (
        os.environ.get("DASHBOARD_ENABLED", "").lower() == "true"
        and os.environ.get("DASHBOARD_MODE") == "api"
    )
    token_file = Path(os.environ.get("CLOUDFLARED_TOKEN_FILE", str(ROOT / "cloudflared-token.txt")))
    if not token_file.is_absolute():
        token_file = ROOT / token_file
    binary = os.environ.get("CLOUDFLARED_EXECUTABLE", "cloudflared")
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    stopped = False

    def shutdown(signum, frame):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    bot = subprocess.Popen([sys.executable, str(ROOT / "start.py")], cwd=ROOT, creationflags=flags)
    connector = None
    retry_at, delay = 0, 1
    try:
        if enabled and not token_file.is_file():
            print(
                "Tunnel token file missing; Meyaya continues without remote dashboard connectivity.",
                flush=True,
            )
            enabled = False
        while not stopped and bot.poll() is None:
            if (
                enabled
                and time.monotonic() >= retry_at
                and (connector is None or connector.poll() is not None)
            ):
                try:
                    # Token is never a command-line argument or printed by this launcher.
                    # Suppress connector output; use Cloudflare's connector status for diagnosis.
                    connector = subprocess.Popen(
                        [
                            binary,
                            "--no-autoupdate",
                            "tunnel",
                            "run",
                            "--token-file",
                            str(token_file),
                        ],
                        cwd=ROOT,
                        creationflags=flags,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        env=connector_environment(),
                    )
                    print("Tunnel connector launched.", flush=True)
                except OSError:
                    print(
                        "Tunnel connector unavailable; bot continues. Verify cloudflared installation.",
                        flush=True,
                    )
                retry_at = time.monotonic() + delay
                delay = min(60, delay * 2)
            time.sleep(0.5)
    finally:
        for child in (connector, bot):
            if child and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
    return bot.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())
