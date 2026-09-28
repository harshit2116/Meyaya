"""Bounded numeric callback timings, isolated across concurrent commands."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import time

from bot.logging.telemetry import event

_active = ContextVar('command_timing', default=None)
STAGES = ('database_ms', 'context_ms', 'quota_ms', 'ai_ms', 'discord_metadata_ms', 'asset_fetch_ms', 'render_ms', 'image_queue_ms', 'delivery_ms')


def add_stage(name, elapsed_ms):
    active = _active.get()
    if active is not None and name in STAGES and not active['closed']:
        active['stages'][name] = active['stages'].get(name, 0) + max(0, elapsed_ms)


@contextmanager
def timing_stage(name):
    started = time.perf_counter()
    try:
        yield
    finally:
        add_stage(name, (time.perf_counter() - started) * 1000)


def install_command_timing(bot):
    for command in bot.walk_commands():
        if getattr(command.callback, '_meyaya_timed', False):
            continue
        callback = command.callback

        def wrap(callback, command):
            @wraps(callback)
            async def run(*args, **kwargs):
                ctx = args[1] if command.cog is not None else args[0]
                state = {'stages': {}, 'closed': False}
                token = _active.set(state)
                started = time.perf_counter()
                status = 'error'
                try:
                    result = await callback(*args, **kwargs)
                    status = 'success'
                    return result
                except BaseException as error:
                    if type(error).__name__ == 'CancelledError':
                        status = 'cancelled'
                    raise
                finally:
                    elapsed = (time.perf_counter() - started) * 1000
                    state['closed'] = True
                    _active.reset(token)
                    event('command_timing', command=command.qualified_name,
                          guild_id=getattr(getattr(ctx, 'guild', None), 'id', None),
                          total_ms=round(elapsed, 2),
                          work_ms=round(max(0, elapsed - state['stages'].get('delivery_ms', 0)), 2),
                          status=status, stages={key: round(value, 2) for key, value in state['stages'].items()},
                          invocation='slash' if getattr(ctx, 'interaction', None) else 'prefix')
            run._meyaya_timed = True
            return run

        command.callback = wrap(callback, command)
        app_command = getattr(command, 'app_command', None)
        if app_command is not None:
            app_command._callback = command.callback
