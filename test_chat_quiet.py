"""Quiet responses and absent context must not masquerade as service failures."""

from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

import pytest

from bot.cogs.chat import ChatCog
from bot.services.autoresponder import is_conversation_closing
from bot.services.llm import LLMReply
from bot.prompts.composer import build_system_instruction
from test_chat_batching import make_bot, make_message, prepare_cog


@pytest.mark.parametrize("text", ["thanks!", "Thank you 💗", "tysm", "goodnight", "bye", "okay thanks"])
def test_pure_closings_are_quiet(text):
    assert is_conversation_closing(text)


@pytest.mark.parametrize("text", ["thanks, can you explain that?", "okay fix my banner",
                                  "thanks but I meant Harshu", "goodnight why are you sad",
                                  "okay?", "I'm not okay"])
def test_questions_corrections_and_disclosures_are_not_closings(text):
    assert not is_conversation_closing(text)


def test_okay_preserves_question_answers_and_unknown_context():
    assert not is_conversation_closing("okay", previous_text="Want a hug?")
    assert not is_conversation_closing("okay")
    assert is_conversation_closing("okay", previous_text="That is the final result.")
    assert not is_conversation_closing("thanks", has_attachments=True)


@pytest.mark.asyncio
async def test_closing_skips_generation_and_queue():
    bot = make_bot()
    cog = prepare_cog(bot)
    msg = make_message(bot, 1, "thanks!")
    await cog.on_message(msg)
    cog._respond_to_message.assert_not_awaited()
    msg.reply.assert_not_awaited()
    assert not cog._chat_conversations


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_failed", [False, True])
async def test_silence_and_service_failure_have_distinct_outcomes(provider_failed):
    bot = make_bot()
    history = NS(get_history=AsyncMock(return_value=[]), append_turn=AsyncMock())
    bot.build_chat_memory_service = lambda: history
    bot.generate_chat = AsyncMock(return_value=None if provider_failed else LLMReply(
        text="NO_REPLY", memories=[], lore=[], actions=[], commands=[]))
    cog = ChatCog(bot)
    cog._build_context_lines = AsyncMock(return_value=[])
    cog._load_memories = AsyncMock(return_value=[])
    cog._load_server_lore = AsyncMock(return_value=[])
    cog._usable_custom_emojis = lambda _: ()
    cog._run_natural_command = AsyncMock()
    cog._record_meyaya_conversation = AsyncMock()
    msg = make_message(bot, 1, "okay")
    with patch("bot.cogs.chat.background_typing"), patch("bot.cogs.chat.health.capture", return_value="MY-TEST"):
        await cog._respond_to_message(msg, "okay", None)
    if provider_failed:
        msg.reply.assert_awaited_once()
        assert "AI service isn't available" in msg.reply.await_args.args[0]
        assert "MY-TEST" in msg.reply.await_args.args[0]
    else:
        msg.reply.assert_not_awaited()
    history.append_turn.assert_not_awaited()
    cog._run_natural_command.assert_not_awaited()
    cog._record_meyaya_conversation.assert_not_awaited()
    instruction = bot.generate_chat.await_args.args[1]
    assert "AVAILABLE RECALL EVIDENCE: 0 stored facts" in instruction
    assert "not proof that a conversation never happened" in instruction
    assert "Do not claim a database outage" in instruction


def test_chat_silence_rules_preserve_substantive_batch_requests():
    prompt = build_system_instruction(context_lines=[])
    assert "exactly NO_REPLY" in prompt
    assert "answer the request" in prompt
