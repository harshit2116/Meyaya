import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

import discord
import pytest
from discord.ext import commands
from sqlalchemy.exc import SQLAlchemyError

from bot.app import MeyayaBot
from bot.cogs.chat import ChatCog
from bot.services.optional_context import OptionalContext
from bot.logging.telemetry import OperationalTelemetry
from bot.utils.command_timing import install_command_timing, timing_stage, add_stage


@pytest.mark.asyncio
async def test_optional_timeout_closes_session_and_backoff_skips_factory():
    reads = OptionalContext(timeout=.01, cooldown=5)
    closed, calls = [], []
    @asynccontextmanager
    async def session():
        try:
            yield
        finally:
            closed.append(True)
    async def slow():
        calls.append(True)
        async with session():
            await asyncio.sleep(1)
    assert await reads.read('profile', slow) == []
    assert closed == [True]
    assert await reads.read('profile', slow) == []
    assert len(calls) == 1
    reads._retry_at['profile'] = 0
    assert await reads.read('profile', AsyncMock(return_value=['Recovered'])) == ['Recovered']


@pytest.mark.asyncio
async def test_optional_reads_do_not_mask_cancellation_or_programming_bugs():
    reads = OptionalContext()
    with pytest.raises(asyncio.CancelledError):
        await reads.read('lore', AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(TypeError):
        await reads.read('lore', AsyncMock(side_effect=TypeError('bug')))
    assert await reads.read('lore', AsyncMock(side_effect=SQLAlchemyError('unavailable'))) == []


@pytest.mark.asyncio
async def test_verified_identity_survives_profile_failure_without_claiming_single():
    bot = NS(user=None, prefix_for_guild=lambda _: 'uwu', get_cog=lambda _: None, walk_commands=lambda: [])
    cog = ChatCog(bot)
    cog._profile_context_lines = AsyncMock(side_effect=SQLAlchemyError('database down'))
    message = NS(author=NS(id=123, name='member', display_name='Member'), guild=NS(id=1, name='Server'),
                 mentions=[], content='hello')
    with patch('bot.prompts.command_knowledge.command_knowledge', return_value=['Command knowledge retained']):
        lines = await cog._build_context_lines(message)
    assert any('AUTHORITATIVE FAMILY IDENTITY' in line for line in lines)
    assert 'Command knowledge retained' in lines
    assert not any('currently single' in line for line in lines)


@pytest.mark.asyncio
async def test_required_quota_failure_never_calls_model_and_refund_failure_does_not_hide_result():
    provider = NS(generate=AsyncMock(return_value=NS(text='')))
    bot = NS(usage=NS(reserve=AsyncMock(side_effect=TimeoutError), refund=AsyncMock()), _llm_provider=provider)
    with pytest.raises(TimeoutError):
        await MeyayaBot.generate_chat(bot, 1, 'system', 'message')
    provider.generate.assert_not_called()
    bot.usage.reserve.side_effect = None
    bot.usage.reserve.return_value = 'day'
    bot.usage.refund.side_effect = SQLAlchemyError('unavailable')
    assert await MeyayaBot.generate_chat(bot, 1, 'system', 'message') is provider.generate.return_value


@pytest.mark.asyncio
async def test_command_timing_prefix_hybrid_errors_and_concurrent_stage_isolation():
    bot = commands.Bot(command_prefix='uwu ', intents=discord.Intents.none(), help_command=None)
    @bot.hybrid_command()
    async def fast(ctx):
        with timing_stage('database_ms'):
            await asyncio.sleep(.001)
        add_stage('delivery_ms', ctx.delivery)
        if ctx.delivery == 2:
            raise ValueError('secret argument must not be logged')
        return 'ok'
    install_command_timing(bot)
    callback = fast.callback
    install_command_timing(bot)
    assert fast.callback is callback
    events = []
    with patch('bot.utils.command_timing.event', side_effect=lambda name, **fields: events.append({'event': name, **fields})):
        first = NS(guild=NS(id=1), interaction=None, delivery=1)
        second = NS(guild=NS(id=2), interaction=object(), delivery=2)
        result = await asyncio.gather(fast.callback(first), fast.app_command._do_call(second, {}), return_exceptions=True)
    assert result[0] == 'ok' and isinstance(result[1], discord.app_commands.CommandInvokeError)
    assert len([row for row in events if row['event'] == 'command.started']) == 2
    events = [row for row in events if row['event'] == 'command_timing']
    assert len(events) == 2
    assert {row['guild_id']: row['stages']['delivery_ms'] for row in events} == {1: 1, 2: 2}
    assert {row['status'] for row in events} == {'success', 'error'}
    assert 'secret' not in json.dumps(events)
    await bot.close()


def test_command_telemetry_is_bounded_server_scoped_and_separate_from_ai():
    store = OperationalTelemetry(capacity=2)
    for guild_id, value in [(1, 100), (2, 200), (2, 400)]:
        store.record({'event': 'command_timing', 'command': 'help', 'guild_id': guild_id, 'status': 'success',
                      'total_ms': value, 'stages': {'delivery_ms': 10, 'secret_prompt': 'must not retain'},
                      'arguments': 'must not retain'})
    snapshot = store.snapshot(2)
    assert snapshot['summary']['requests'] == 0
    row = snapshot['commands']['groups'][0]
    assert row['calls'] == 2 and row['average_ms'] == 300
    assert row['stages'] == {'delivery_ms': 10}
    assert not store.snapshot(1)['commands']['groups']
    assert 'must not retain' not in json.dumps(snapshot)
