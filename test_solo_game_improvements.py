"""Gameplay invariants and delivery failures for the single-player games."""

import asyncio
from copy import deepcopy
from random import Random
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock

import pytest

from bot.cogs.solo_games import SoloGamesCog, SoloView
from bot.data.solo_games import ADVENTURES, CASES, PERSONALITIES
from bot.services.solo_games import SoloGame


def click(user=1):
    return NS(user=NS(id=user), response=NS(defer=AsyncMock(), send_message=AsyncMock()),
              followup=NS(send=AsyncMock()), edit_original_response=AsyncMock())


def assert_presentation(game):
    title, text, fields = game.presentation()
    assert 0 < len(title) <= 256 and 0 < len(text) <= 4096
    assert len(fields) <= 25
    assert all(len(name) <= 256 and 0 < len(value) <= 1024 for name, value, _ in fields)
    assert len(title) + len(text) + sum(len(n) + len(v) for n, v, _ in fields) < 5700
    assert all(len(action.label) <= 80 for action in game.actions())


@pytest.mark.parametrize("index", range(len(ADVENTURES)))
def test_every_escape_path_terminates_and_each_adventure_can_win_or_fail(index):
    initial = SoloGame("escape", rng=Random(1))
    initial.adventure_index = index
    initial.shuffle_options()
    pending, endings, visited = [initial], set(), 0
    while pending:
        game = pending.pop()
        visited += 1
        assert visited < 1000
        assert 0 <= game.time_left <= 8 and game.step <= 5
        assert_presentation(game)
        if game.done:
            endings.add(game.title)
            assert len(game.history) == game.step
            continue
        actions = game.actions()
        assert any(a.enabled for a in actions)
        assert len({a.key for a in actions}) == len(actions)
        for action in actions:
            branch = deepcopy(game)
            if action.enabled:
                branch.apply(action.key)
                assert branch.step == game.step + 1
                assert branch.time_left < game.time_left
                pending.append(branch)
            else:
                with pytest.raises(ValueError):
                    branch.apply(action.key)
                assert branch.history == game.history
    assert {ADVENTURES[index].special_ending, "Made it out", "The scenic rescue"} <= endings


def test_escape_item_has_later_effect_and_alternate_route():
    game = SoloGame("escape")
    game.adventure_index = 0
    game.shuffle_options()
    game.apply("map")
    assert "floor map" in game.inventory and game.scene == "passage"
    assert next(a for a in game.actions() if a.key == "marked").enabled
    assert not next(a for a in game.actions() if a.key == "radio").enabled
    other = SoloGame("escape")
    other.adventure_index = 0
    other.shuffle_options()
    other.apply("toys")
    assert other.scene == "maintenance"


@pytest.mark.parametrize("case_index", range(len(CASES)))
@pytest.mark.parametrize("accused", ["a", "b", "c"])
def test_detective_requires_evidence_and_consistent_explanation(case_index, accused):
    game = SoloGame("detective", rng=Random(case_index))
    game.case_index = case_index
    assert len(set(game.names.values())) == 3
    with pytest.raises(ValueError):
        game.apply("accuse")
    game.apply("clue:1")
    with pytest.raises(ValueError):
        game.apply("accuse")
    with pytest.raises(ValueError):
        game.apply("clue:1")
    game.apply("clue:2")
    assert_presentation(game)
    game.apply("accuse")
    assert game.accusing
    game.apply("back")
    assert not game.accusing and game.clues == [1, 2]
    game.apply("clue:0")
    game.apply("clue:3")
    assert_presentation(game)
    game.apply("accuse")
    game.apply("accuse:" + accused)
    assert game.done and game.correct == (accused == "c")
    assert all(name in game.result for name in game.names.values())
    assert "{" not in game.result
    assert_presentation(game)


@pytest.mark.parametrize("answers,leaders", [
    ([0] * 6, (0,)), ([1] * 6, (1,)), ([2] * 6, (2,)),
    ([0, 1] * 3, (0, 1)), ([0, 2] * 3, (0, 2)),
    ([1, 2] * 3, (1, 2)), ([0, 1, 2] * 2, (0, 1, 2)),
])
def test_personality_scoring_and_all_blended_ties(answers, leaders):
    game = SoloGame("personalitytest", rng=Random(7))
    assert len({q[0] for q in game.questions}) == 6
    for i, answer in enumerate(answers):
        assert_presentation(game)
        assert not game.done
        game.apply(str(answer))
        assert sum(game.scores) == i + 1
    assert game.done and game.personality == leaders
    assert game.title == PERSONALITIES[leaders][0]
    assert_presentation(game)


@pytest.mark.parametrize("kind", ["escape", "detective", "personalitytest"])
def test_replay_and_option_order_are_varied(kind):
    first = SoloGame(kind, rng=Random(1))
    second = SoloGame(kind, previous=first, rng=Random(1))
    assert second.adventure_index != first.adventure_index
    assert second.case_index != first.case_index
    orders = {tuple(a.key for a in SoloGame(kind, rng=Random(seed)).actions()) for seed in range(20)}
    if kind != "detective":
        assert len(orders) > 1
    else:
        assert len({tuple(SoloGame(kind, rng=Random(seed)).suspect_order) for seed in range(20)}) > 1


@pytest.mark.asyncio
async def test_owner_stale_click_and_lock_guards():
    view = SoloView(1, "personalitytest", Mock())
    outsider = click(2)
    assert not await view.interaction_check(outsider)
    assert outsider.response.send_message.await_args.kwargs["ephemeral"]
    await view.choose(click(), "1", 0)
    await view.choose(click(), "2", 0)
    assert view.step == 1 and view.game.scores == [0, 1, 0]
    busy = click()
    async with view.lock:
        await view.choose(busy, "2", 1)
    assert view.step == 1
    busy.followup.send.assert_awaited_once()
    view.dispose()


@pytest.mark.asyncio
async def test_edit_failure_rolls_back_without_consuming_choice_or_slot():
    release = Mock()
    view = SoloView(1, "personalitytest", release)
    buttons = list(view.children)
    bad = click()
    bad.edit_original_response.side_effect = RuntimeError("network unavailable")
    with pytest.raises(RuntimeError):
        await view.choose(bad, "1", 0)
    assert view.step == view.revision == 0 and view.game.scores == [0, 0, 0]
    assert list(view.children) == buttons
    release.assert_not_called()
    await view.choose(click(), "2", 0)
    assert view.game.scores == [0, 0, 1]
    view.dispose()


@pytest.mark.asyncio
async def test_quit_replay_timeout_and_old_view_cannot_release_new_game():
    cog = SoloGamesCog(NS())
    ctx = NS(author=NS(id=1), guild=NS(id=10), send=AsyncMock())
    await cog.start(ctx, "escape")
    view = ctx.send.await_args.kwargs["view"]
    previous = view.game.adventure_index
    await view.choose(click(), "quit", 0)
    assert not cog.active and view in cog.views
    view.started -= 3
    await view.choose(click(), "replay", 1)
    assert cog.active[(10, 1)] is view and not view.closed
    assert view.game.adventure_index != previous
    await view.choose(click(), "quit", 2)
    await cog.start(ctx, "detective")
    new_view = ctx.send.await_args.kwargs["view"]
    assert new_view is not view
    view.started -= 3
    blocked = click()
    await view.choose(blocked, "replay", 3)
    blocked.followup.send.assert_awaited_once()
    await view.on_timeout()
    assert cog.active[(10, 1)] is new_view
    await cog.cog_unload()
    assert not cog.active and not cog.views


@pytest.mark.asyncio
async def test_replay_edit_failure_releases_reservation():
    view = SoloView(1, "detective", Mock(), acquire=Mock(return_value=True))
    await view.choose(click(), "quit", 0)
    view.started -= 3
    old_game = view.game
    bad = click()
    bad.edit_original_response.side_effect = RuntimeError("no connection")
    with pytest.raises(RuntimeError):
        await view.choose(bad, "replay", 1)
    assert view.game is old_game and view.closed and not view.has_slot
    assert view.revision == 1 and view.release.call_count == 2
    view.dispose()


@pytest.mark.asyncio
async def test_timeout_release_once_and_preserve_completed_result():
    view = SoloView(1, "personalitytest", Mock())
    view.message = NS(edit=AsyncMock())
    for i in range(6):
        await view.choose(click(), str(i % 3), i)
    title = view.game.title
    await view.on_timeout()
    await view.on_timeout()
    view.release.assert_called_once()
    assert view.game.title == title
    assert view.message.edit.await_args.kwargs["embed"].title.endswith(title)
    assert view.game.result in view.message.edit.await_args.kwargs["embed"].description
    assert view.disposed and not view.children


@pytest.mark.asyncio
async def test_cancelled_start_and_inactivity_cleanup():
    cog = SoloGamesCog(NS())
    ctx = NS(author=NS(id=1), guild=None, send=AsyncMock(side_effect=asyncio.CancelledError()))
    with pytest.raises(asyncio.CancelledError):
        await cog.start(ctx, "escape")
    assert not cog.active and not cog.views
    ctx.send = AsyncMock(return_value=NS(edit=AsyncMock()))
    await cog.start(ctx, "escape")
    view = cog.active[(0, 1)]
    await view.on_timeout()
    assert not cog.active and not cog.views
    assert "three minutes" in view.game.result
