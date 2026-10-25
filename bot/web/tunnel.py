"""Own an encrypted SSH or Session Manager forward for the local console."""
import asyncio
import os
import socket
import subprocess
import json
import shutil
from pathlib import Path
from urllib.parse import urlsplit


class TunnelError(RuntimeError):
    """A credential-free connection diagnosis suitable for the launcher."""


async def start_tunnel(settings):
    target = urlsplit(settings.dashboard_remote_url)
    if target.scheme != 'http' or target.hostname != '127.0.0.1' or not target.port:
        raise ValueError('Tunnel mode requires http://127.0.0.1:<local tunnel port>')
    ssm_instance = getattr(settings, 'dashboard_ssm_instance', '')
    if not ssm_instance and (settings.dashboard_ssh_host.startswith('-') or not settings.dashboard_ssh_key):
        raise ValueError('Configure an SSH host and private key path')
    # Do not attach a token-bearing client to an unrelated existing listener.
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', target.port))
    if ssm_instance:
        process = await _start_ssm(settings, target.port)
    else:
        key = Path(settings.dashboard_ssh_key).expanduser().resolve(strict=True)
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
                raise TunnelError('AWS tunnel exited. Check AWS credentials and Session Manager access.' if ssm_instance else
                                  'SSH connection failed. Check the AWS inbound SSH rule for your current IP, the key, and known hosts.')
            try:
                reader, writer = await asyncio.open_connection('127.0.0.1', target.port)
                writer.close()
                await writer.wait_closed()
                return process
            except OSError:
                await asyncio.sleep(.25)
        raise TunnelError('AWS tunnel did not become ready. Check connectivity and AWS access.')
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
    session = getattr(process, '_meyaya_ssm', None)
    if session is not None:
        process._meyaya_ssm = None
        client, session_id = session
        try:
            await asyncio.to_thread(client.terminate_session, SessionId=session_id)
        except Exception:
            pass  # Local cleanup must still finish if AWS connectivity was lost.


async def _start_ssm(settings, local_port):
    """Forward with IAM authentication; no public inbound SSH port is required."""
    plugin = getattr(settings, 'dashboard_ssm_plugin', '') or shutil.which('session-manager-plugin')
    if not plugin or not Path(plugin).is_file():
        raise TunnelError('Install the AWS Session Manager plugin and set DASHBOARD_SSM_PLUGIN to its executable.')
    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        raise TunnelError('Install local dashboard dependencies: python -m pip install ".[dashboard]"') from None
    region = settings.dashboard_aws_region
    parameters = dict(Target=settings.dashboard_ssm_instance,
                      DocumentName='AWS-StartPortForwardingSession',
                      Parameters={'portNumber': ['8080'], 'localPortNumber': [str(local_port)]})
    def connect():
        session = boto3.Session(profile_name=settings.dashboard_aws_profile or None, region_name=region)
        client = session.client('ssm', config=Config(connect_timeout=8, read_timeout=12, retries={'max_attempts': 1}))
        return client, client.start_session(**parameters)
    try:
        client, session = await asyncio.to_thread(connect)
    except Exception:
        raise TunnelError('Cannot start AWS Session Manager. Check your AWS profile login, region, and instance permissions.') from None
    try:
        process = await asyncio.create_subprocess_exec(
            str(plugin), json.dumps(session), region, 'StartSession', settings.dashboard_aws_profile,
            json.dumps(parameters), client.meta.endpoint_url,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
    except BaseException:
        await asyncio.to_thread(client.terminate_session, SessionId=session['SessionId'])
        raise
    process._meyaya_ssm = (client, session['SessionId'])
    return process
