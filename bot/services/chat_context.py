"""Fit final chat requests without dropping the member's current statement."""
from dataclasses import dataclass

from bot.logging.telemetry import event
from bot.prompts.composer import build_system_instruction


class ContextOverflow(ValueError):
    """Mandatory instructions and current input cannot fit the configured cap."""


@dataclass
class PreparedChat:
    instruction: str
    prompt: str
    history: list
    memory_lines: list


def prepare_chat(*, profile, guild_id, context_lines, memory_lines=(), lore_lines=(),
                 prompt, history=(), recent_context='', limit=32000):
    # Never split a serialized prompt on a sentinel that user text can imitate.
    # Quote fields are bounded by the caller before serialization.
    core, optional = [], []
    for line in context_lines:
        if not line:
            continue
        if line.startswith(('Usable custom', 'RECENT DELIVERED', 'AVAILABLE RECALL',
                            'Shared lore', 'Recent profile', 'PROFILE', 'Profile review',
                            "Meyaya's available public command names", 'When someone asks to improve', '/')):
            optional.append(line[:1800])
        else:
            core.append(line)
    memories = list(memory_lines)
    lore = list(lore_lines)
    context = core + optional
    def compose():
        return build_system_instruction(profile=profile, guild_id=guild_id,
            context_lines=context, memory_lines=memories, lore_lines=lore)
    instruction = compose()
    # Reserve useful room for the actual conversation before adding optional recall.
    reserve = min(4000, max(0, limit // 8))
    while len(instruction) + len(prompt) > limit - reserve and (lore or optional or len(memories) > 4):
        if lore:
            lore.pop()
        elif optional:
            context.remove(optional.pop())
        else:
            memories.pop()
        instruction = compose()
    while len(instruction) + len(prompt) > limit and memories:
        memories.pop()
        instruction = compose()
    if len(instruction) + len(prompt) > limit:
        event('chat_context_overflow', profile=profile, instruction_chars=len(instruction),
              current_chars=len(prompt), limit=limit)
        raise ContextOverflow('Internal context exceeds the available budget')
    remaining = limit - len(instruction) - len(prompt)
    # Most recent complete exchanges come before ambient channel chatter.
    kept, used = [], 0
    for item in reversed(history):
        size = len(item.get('content', ''))
        if used + size > remaining:
            break
        kept.insert(0, item)
        used += size
    while kept and kept[0].get('role') != 'user':
        used -= len(kept.pop(0).get('content', ''))
    ambient = recent_context if len(recent_context) <= remaining - used else ''
    total = len(instruction) + len(prompt) + used + len(ambient)
    assert total <= limit
    event('chat_context_size', profile=profile, instruction_chars=len(instruction),
          current_chars=len(prompt), history_chars=used, ambient_chars=len(ambient),
          memory_count=len(memories), total_chars=total, limit=limit)
    return PreparedChat(instruction, ambient + prompt, kept, memories)
