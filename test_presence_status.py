from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from bot.cogs.presence import PresenceCog, identity_activity, STATUS_TEXT, STATUS_EMOJI_ID


def test_identity_custom_status_payload():
    payload = identity_activity().to_dict()
    assert payload["type"] == 4
    assert payload["state"] == STATUS_TEXT
    assert payload["emoji"]["id"] == STATUS_EMOJI_ID
    assert payload["emoji"]["name"] == "Meyaya"
    assert len(STATUS_TEXT) <= 128


@pytest.mark.asyncio
async def test_dnd_identity_reapplied_on_ready_without_rotation():
    bot = SimpleNamespace(change_presence=AsyncMock())
    cog = PresenceCog(bot)
    for _ in range(2):
        await cog.on_ready()
        assert bot.change_presence.call_args.kwargs["status"] == discord.Status.dnd
        assert bot.change_presence.call_args.kwargs["activity"].name == STATUS_TEXT
    assert bot.change_presence.await_count == 2
    assert not hasattr(cog, "rotate")


@pytest.mark.asyncio
async def test_presence_failure_does_not_abort_ready():
    bot = SimpleNamespace(change_presence=AsyncMock(side_effect=ConnectionError("offline")))
    await PresenceCog(bot).on_ready()
