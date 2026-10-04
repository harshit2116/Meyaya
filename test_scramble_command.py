from io import BytesIO
from random import Random
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image

from bot.cogs.fun import FunCog
from bot.data.help_catalog import COMMANDS
from bot.services.scramble import GOAL, SIZE, neighbours, prepare_avatar, render_board, shuffled_board
from bot.views.scramble import ScrambleView, TileButton


def avatar_bytes():
    output = BytesIO()
    Image.new("RGB", (256, 256), "#ed728e").save(output, "PNG")
    return output.getvalue()


def test_shuffle_is_solvable_and_not_trivial():
    for seed in range(200):
        board = shuffled_board(Random(seed))
        assert sorted(board) == list(range(9))
        numbered = [i for i in board if i]
        inversions = sum(a > b for i, a in enumerate(numbered) for b in numbered[i + 1:])
        assert inversions % 2 == 0
        assert sum(a != b for a, b in zip(board, GOAL)) >= 6
    assert neighbours(0) == (1, 3)
    assert neighbours(4) == (1, 3, 5, 7)


@pytest.mark.parametrize("finished", [False, True])
def test_avatar_board_quality_and_bounds(finished, tmp_path):
    avatar = prepare_avatar(avatar_bytes())
    data = render_board(avatar, shuffled_board(Random(4)), "W" * 100, finished=finished)
    assert len(data) < 2 * 1024 * 1024
    with Image.open(BytesIO(data)) as result:
        assert result.size == SIZE
        assert result.getpixel((700, 230)) == (237, 114, 142)
    with Image.open(BytesIO(data)) as result:
        result.verify()


def test_bad_avatar_rejected():
    with pytest.raises(ValueError):
        prepare_avatar(b"")
    with pytest.raises(OSError):
        prepare_avatar(b"invalid")


def interaction(user=1):
    return NS(user=NS(id=user), response=NS(defer=AsyncMock(), send_message=AsyncMock()),
              followup=NS(send=AsyncMock()), edit_original_response=AsyncMock())


def make_view():
    return ScrambleView(1, "Ayaya", prepare_avatar(avatar_bytes()), Mock())


@pytest.mark.asyncio
async def test_owner_only_and_buttons_match_board():
    view = make_view()
    other = interaction(2)
    assert not await view.interaction_check(other)
    assert other.response.send_message.await_args.kwargs["ephemeral"]
    assert await view.interaction_check(interaction())
    for button in view.children:
        if isinstance(button, TileButton):
            assert button.disabled == (button.position not in neighbours(view.board.index(0)))
    view.finish()
    view.finish()
    view.release.assert_called_once()


@pytest.mark.asyncio
async def test_winning_move_and_reveal():
    view = make_view()
    view.board = (1, 2, 3, 4, 5, 6, 7, 0, 8)
    view.sync_buttons()
    click = interaction()
    await view.move(click, 8)
    assert view.board == GOAL and view.moves == 1 and view.ended
    assert all(button.disabled for button in view.children)
    assert "restored" in click.edit_original_response.await_args.kwargs["embed"].description
    view.release.assert_called_once()


@pytest.mark.asyncio
async def test_failed_update_rolls_back_and_busy_click_does_not_move():
    view = make_view()
    initial = view.board
    click = interaction()
    click.edit_original_response.side_effect = RuntimeError("network")
    with pytest.raises(RuntimeError):
        await view.move(click, neighbours(view.board.index(0))[0])
    assert view.board == initial and view.moves == 0 and not view.ended
    async with view.lock:
        click = interaction()
        await view.move(click, neighbours(view.board.index(0))[0])
        click.followup.send.assert_awaited_once()
    view.finish()


@pytest.mark.asyncio
async def test_timeout_releases_slot_disables_buttons_and_retains_image():
    view = make_view()
    view.message = NS(edit=AsyncMock())
    await view.on_timeout()
    assert view.ended and all(button.disabled for button in view.children)
    assert "attachments" not in view.message.edit.await_args.kwargs
    view.release.assert_called_once()


@pytest.mark.asyncio
async def test_give_up_reveals_and_fixed_clock_cancels():
    view = make_view()
    view.start_clock()
    deadline = view.deadline
    click = interaction()
    await view.give_up.callback(click)
    assert view.ended and view.deadline == deadline
    assert "complete picture" in click.edit_original_response.await_args.kwargs["embed"].description
    await __import__("asyncio").sleep(0)
    assert view.expiry_task.cancelled()


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit", [False, True])
async def test_command_target_no_ai_and_duplicate_guard(explicit):
    author = NS(id=1, display_name="Ayaya")
    member = NS(id=2, display_name="Haru")
    ctx = NS(author=author, defer=AsyncMock(), send=AsyncMock())
    bot = NS(build_llm_provider=AsyncMock())
    cog = FunCog(bot)
    cog._card_avatar = AsyncMock(return_value=avatar_bytes())
    await FunCog.scramble.callback(cog, ctx, member if explicit else None)
    view = ctx.send.await_args.kwargs["view"]
    assert view.name == ("Haru" if explicit else "Ayaya")
    assert 1 in cog.scramble_players
    assert len(cog.scramble_views) == 1
    await FunCog.scramble.callback(cog, ctx)
    assert "current puzzle" in ctx.send.await_args.args[0]
    bot.build_llm_provider.assert_not_called()
    await cog.cog_unload()
    assert not cog.scramble_players and not cog.scramble_views


@pytest.mark.asyncio
async def test_failed_avatar_releases_player():
    cog = FunCog(NS())
    cog._card_avatar = AsyncMock(return_value=b"")
    ctx = NS(author=NS(id=1, display_name="Ayaya"), defer=AsyncMock(), send=AsyncMock())
    await FunCog.scramble.callback(cog, ctx)
    assert not cog.scramble_players
    assert "avatar" in ctx.send.await_args.args[0]


def test_discoverable_hybrid():
    assert FunCog.scramble.app_command.name == "scramble"
    assert any(item.name == "scramble" for item in COMMANDS)
