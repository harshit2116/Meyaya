"""Explicit application-owned game phase transitions."""

from enum import StrEnum


class GamePhase(StrEnum):
    LOBBY = "LOBBY"
    COLLECTING = "COLLECTING"
    LOCKED = "LOCKED"
    JUDGING = "JUDGING"
    RESULTS = "RESULTS"
    CLOSED = "CLOSED"
    CLARIFYING = "CLARIFYING"


TRANSITIONS = {
    GamePhase.LOBBY: {GamePhase.COLLECTING, GamePhase.CLOSED},
    GamePhase.COLLECTING: {GamePhase.LOCKED, GamePhase.CLOSED},
    GamePhase.LOCKED: {GamePhase.JUDGING, GamePhase.CLOSED},
    GamePhase.JUDGING: {GamePhase.RESULTS, GamePhase.LOCKED, GamePhase.CLOSED},
    GamePhase.RESULTS: {GamePhase.CLOSED},
    GamePhase.CLOSED: set(),
    GamePhase.CLARIFYING: {GamePhase.LOCKED, GamePhase.CLOSED},
}


def validate_transition(current: str, target: str, *, court: bool = False) -> None:
    before, after = GamePhase(current), GamePhase(target)
    allowed = TRANSITIONS[before]
    if court and before == GamePhase.JUDGING and after == GamePhase.CLARIFYING:
        return
    if after not in allowed:
        raise ValueError(f"Invalid game transition: {before} -> {after}")
