"""Per-turn terminal metadata, with no retained conversation text."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_turn: ContextVar[dict[str, str] | None] = ContextVar('chat_turn_outcome', default=None)


@contextmanager
def track_turn(turn_id: object) -> Iterator[dict[str, str]]:
    result = {'turn_id': str(turn_id), 'outcome': 'not_delivered'}
    token = _turn.set(result)
    try:
        yield result
    finally:
        _turn.reset(token)


def outcome(value: str) -> None:
    result = _turn.get()
    if result is not None:
        if value == 'provider_unavailable' and result['outcome'] == 'provider_deadline':
            return
        result['outcome'] = value
