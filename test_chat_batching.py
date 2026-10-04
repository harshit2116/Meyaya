"""Burst coalescing must preserve ordering, member boundaries and chat history."""

import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock

import pytest

from bot.cogs.chat import ChatCog, ChatEntry, ReplyContext, MAX_BATCH_MESSAGES
from bot.services.llm import LLMReply


def make_bot(**settings):
    identity = NS(id=99)
    return NS(
        user=identity,
        settings=NS(ai_max_concurrent=2, ai_queue_size=4,
                    chat_batch_delay_seconds=settings.get("delay", 0.02),
                    chat_batch_max_wait_seconds=0.08),
        chat_blacklist=NS(is_blocked=lambda *_: False, inspect=AsyncMock(return_value=False)),
        get_cog=lambda _: None, chat_allowed=lambda *_: True,
        get_context=AsyncMock(return_value=NS(valid=False, prefix=None)),
        build_llm_provider=lambda: object(),
        request_log=NS(record_message=AsyncMock()),
    )


def make_message(bot, message_id, text="hello", *, user_id=11, channel_id=7, addressed=True):
    return NS(
        id=message_id, author=NS(id=user_id, bot=False, name=f"user{user_id}", display_name="Same name"),
        guild=NS(id=2), channel=NS(id=channel_id),
        reference=None, mention_everyone=False,
        mentions=[bot.user] if addressed else [],
        content=f"<@99> {text}" if addressed else text, reply=AsyncMock(),
    )


async def wait_for_conversation(cog, key=(2, 7, 11)):
    async with asyncio.timeout(1):
        while key not in cog._chat_conversations:
            await asyncio.sleep(0)


def prepare_cog(bot):
    cog = ChatCog(bot)
    cog._resolve_reply_context = AsyncMock(return_value=None)
    cog._maybe_proactive_reply = AsyncMock()
    cog._respond_to_message = AsyncMock()
    return cog


@pytest.mark.asyncio
async def test_mention_command_skips_reply_resolution_and_chat():
    bot = make_bot()
    bot.get_context = AsyncMock(return_value=NS(valid=True, prefix="<@99> "))
    cog = prepare_cog(bot)
    message = make_message(bot, 1, "duck")
    message.reference = NS(message_id=50)
    await cog.on_message(message)
    cog._resolve_reply_context.assert_not_awaited()
    cog._respond_to_message.assert_not_awaited()
    bot.get_context.assert_awaited_once()


@pytest.mark.asyncio
async def test_explicit_thanks_skips_reply_resolution():
    bot = make_bot()
    cog = prepare_cog(bot)
    message = make_message(bot, 1, "thanks!")
    message.reference = NS(message_id=50)
    await cog.on_message(message)
    cog._resolve_reply_context.assert_not_awaited()
    cog._respond_to_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_three_fast_messages_make_one_turn_including_unmentioned_followups():
    bot = make_bot()
    cog = prepare_cog(bot)
    messages = [make_message(bot, 1, "I changed my profile"),
                make_message(bot, 2, "the banner is blue", addressed=False),
                make_message(bot, 3, "what do you think?", addressed=False)]
    worker = asyncio.create_task(cog.on_message(messages[0]))
    await wait_for_conversation(cog)
    await cog.on_message(messages[1])
    await cog.on_message(messages[2])
    await worker
    cog._respond_to_message.assert_awaited_once()
    call = cog._respond_to_message.await_args
    assert call.args[0] is messages[2]
    assert call.args[1] == "I changed my profile\nthe banner is blue\nwhat do you think?"
    assert [entry.message.id for entry in call.kwargs["batch"]] == [1, 2, 3]
    assert cog._active_chats == 0
    assert not cog._chat_conversations


@pytest.mark.asyncio
async def test_next_turn_waits_for_delivery_and_updated_history():
    bot = make_bot()
    history = []
    first_generation = asyncio.Event()
    release_generation = asyncio.Event()
    histories_seen = []

    async def get_history(*_):
        return list(history)

    async def append_turn(channel_id, user_id, text, answer, **kwargs):
        history.extend([{"role": "user", "content": text}, {"role": "assistant", "content": answer}])

    async def generate_chat(*_, history=None, **kwargs):
        histories_seen.append(list(history))
        if len(histories_seen) == 1:
            first_generation.set()
            await release_generation.wait()
        return LLMReply(f"Answer {len(histories_seen)}", [], [], [], [])

    bot.build_chat_memory_service = lambda: NS(get_history=get_history, append_turn=append_turn)
    bot.generate_chat = AsyncMock(side_effect=generate_chat)
    cog = prepare_cog(bot)
    # Exercise the real context, delivery and history path inside the serial queue.
    cog._respond_to_message = ChatCog._respond_to_message.__get__(cog)
    for method in ("_build_context_lines", "_load_memories", "_load_server_lore"):
        setattr(cog, method, AsyncMock(return_value=[]))
    cog._usable_custom_emojis = Mock(return_value=())
    cog._run_natural_command = AsyncMock(return_value=False)
    cog._run_self_action = AsyncMock()
    cog._record_meyaya_conversation = AsyncMock()
    first = make_message(bot, 1, "first question")
    first.channel.typing = lambda: AsyncMock()
    worker = asyncio.create_task(cog.on_message(first))
    await asyncio.wait_for(first_generation.wait(), 1)
    followups = [make_message(bot, 2, "and another thing", addressed=False),
                 make_message(bot, 3, "please explain it", addressed=False)]
    for message in followups:
        message.channel = first.channel
        await cog.on_message(message)
    assert bot.generate_chat.await_count == 1
    release_generation.set()
    await worker
    assert bot.generate_chat.await_count == 2
    assert histories_seen[0] == []
    assert histories_seen[1][-1] == {"role": "assistant", "content": "Answer 1"}
    first.reply.assert_awaited_once_with("Answer 1")
    followups[0].reply.assert_not_awaited()
    followups[1].reply.assert_awaited_once_with("Answer 2")
    assert "and another thing" in history[-2]["content"]
    assert "please explain it" in history[-2]["content"]
    logged_ids = {call.args[0].id for call in bot.request_log.record_message.await_args_list}
    assert logged_ids == {1, 2, 3}


@pytest.mark.asyncio
async def test_member_and_channel_boundaries_are_kept_even_with_identical_names():
    bot = make_bot()
    cog = prepare_cog(bot)
    messages = [make_message(bot, 1, "one"),
                make_message(bot, 2, "two", user_id=22),
                make_message(bot, 3, "three", channel_id=8)]
    await asyncio.gather(*(cog.on_message(message) for message in messages))
    assert cog._respond_to_message.await_count == 3
    assert {call.args[1] for call in cog._respond_to_message.await_args_list} == {"one", "two", "three"}
    assert all("batch" not in call.kwargs for call in cog._respond_to_message.await_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["other_member", "other_reply", "prefix_command"])
async def test_ordinary_chat_and_commands_do_not_join_a_pending_turn(kind):
    bot = make_bot()
    cog = prepare_cog(bot)
    worker = asyncio.create_task(cog.on_message(make_message(bot, 1)))
    await wait_for_conversation(cog)
    message = make_message(bot, 2, "unrelated", addressed=False,
                           user_id=22 if kind == "other_member" else 11)
    if kind == "other_reply":
        message.reference = NS(message_id=55)
        cog._resolve_reply_context.return_value = ReplyContext(55, 22, "Other member", "text", ())
    if kind == "prefix_command":
        bot.get_context.return_value = NS(valid=True, prefix="uwu ")
    await cog.on_message(message)
    await worker
    cog._respond_to_message.assert_awaited_once()
    assert cog._respond_to_message.await_args.args[1] == "hello"


@pytest.mark.asyncio
async def test_pending_messages_and_global_conversations_are_bounded():
    bot = make_bot()
    bot.settings.ai_max_concurrent = 1
    bot.settings.ai_queue_size = 0
    cog = prepare_cog(bot)
    release = asyncio.Event()
    async def wait(*_):
        await release.wait()
    cog._wait_for_chat_batch = wait
    worker = asyncio.create_task(cog.on_message(make_message(bot, 1)))
    await wait_for_conversation(cog)
    for i in range(2, MAX_BATCH_MESSAGES + 1):
        await cog.on_message(make_message(bot, i, f"message {i}"))
    overflow = make_message(bot, 20, "extra message")
    await cog.on_message(overflow)
    overflow.reply.assert_awaited_once()
    other = make_message(bot, 21, "other member", user_id=22, channel_id=8)
    await cog.on_message(other)
    other.reply.assert_awaited_once()
    assert len(cog._chat_conversations) == 1
    assert len(cog._chat_conversations[(2, 7, 11)].entries) == MAX_BATCH_MESSAGES
    release.set()
    await worker


@pytest.mark.asyncio
async def test_unload_cancels_workers_and_releases_admission():
    bot = make_bot()
    cog = prepare_cog(bot)
    generating = asyncio.Event()
    async def generate(*args, **kwargs):
        generating.set()
        await asyncio.Event().wait()
    cog._respond_to_message.side_effect = generate
    worker = asyncio.create_task(cog.on_message(make_message(bot, 1)))
    await asyncio.wait_for(generating.wait(), 1)
    await cog.cog_unload()
    assert worker.cancelled()
    assert not cog._chat_conversations
    assert cog._active_chats == 0


def test_batch_prompt_keeps_each_reply_target_separate():
    bot = make_bot()
    entries = [
        ChatEntry(make_message(bot, 1), "why me?", ReplyContext(
            50, 99, "Meyaya", "", (), command_name="mostlikely",
            command_result_summary='{"selected_member_id":11,"scenario":"be late"}',
        )),
        ChatEntry(make_message(bot, 2), "and this score?", ReplyContext(
            60, 99, "Meyaya", "", (), command_name="ship",
            command_result_summary='{"first_id":11,"second_id":22,"score":73}',
        )),
    ]
    prompt = ChatCog._batch_aware_prompt(entries)
    assert '"reply_to_message_id": 50' in prompt
    assert '"reply_to_message_id": 60' in prompt
    assert "be late" in prompt
    assert "73" in prompt
    assert "Discord user ID 11" in prompt


def test_large_previous_card_context_keeps_recent_complete_turns_within_budget():
    history = [{"role": "user", "content": "x" * 1000},
               {"role": "assistant", "content": "old reply"},
               {"role": "user", "content": "recent question"},
               {"role": "assistant", "content": "recent answer"}]
    fitted = ChatCog._fit_chat_history(history, 40)
    assert fitted == history[2:]
    assert sum(len(row["content"]) for row in fitted) <= 40
    assert len(history) == 4
