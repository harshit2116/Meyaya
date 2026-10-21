"""Own an encrypted SSH forward for the lifetime of the local console."""
import asyncio
import os
import socket
import subprocess
from pathlib import Path
from urllib.parse import urlsplit


async def start_tunnel(settings):
    target = urlsplit(settings.dashboard_remote_url)
    if target.scheme != 'http' or target.hostname != '127.0.0.1' or not target.port:
        raise ValueError('SSH mode requires http://127.0.0.1:<local tunnel port>')
    if settings.dashboard_ssh_host.startswith('-') or not settings.dashboard_ssh_key:
        raise ValueError('Configure an SSH host and private key path')
    key = Path(settings.dashboard_ssh_key).expanduser().resolve(strict=True)
    # Do not attach a token-bearing client to an unrelated existing listener.
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', target.port))
    process = await asyncio.create_subprocess_exec(
        'ssh', '-N', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
        '-o', 'ExitOnForwardFailure=yes', '-o', 'ConnectTimeout=15',
        '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
        '-i', str(key), '-L', f'127.0.0.1:{target.port}:127.0.0.1:8080',
        settings.dashboard_ssh_host,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
    try:
        for _ in range(60):
            if process.returncode is not None:
                raise RuntimeError('SSH tunnel exited; check the key and known-host entry')
            try:
                reader, writer = await asyncio.open_connection('127.0.0.1', target.port)
                writer.close()
                await writer.wait_closed()
                return process
            except OSError:
                await asyncio.sleep(.25)
        raise TimeoutError('SSH tunnel did not start')
    except BaseException:
        await stop_tunnel(process)
        raise


async def stop_tunnel(process):
    if process is not None and process.returncode is None:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), 5)
        except TimeoutError:
            process.kill()
            await process.wait()
