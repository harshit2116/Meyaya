"""Concurrency-safe state and structured judging for anonymous social games."""

from __future__ import annotations

from bot.prompts.social_games import build_game_instructions

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import json
import logging
import re
from secrets import token_urlsafe
from typing import Callable

from bot.data.social_games import GameScenario
from bot.services.llm import LLMProvider
from bot.services.game_engine import validate_transition
from bot.logging.telemetry import event

logger = logging.getLogger(__name__)

DISCORD_MENTION_PATTERN = re.compile(r"<@!?&?\d+>|@everyone|@here", re.IGNORECASE)

MIN_PLAYERS = 2
MAX_PLAYERS = 8
MAX_SUBMISSION_LENGTH = 500
LOBBY_LIFETIME = timedelta(minutes=5)
COLLECTION_LIFETIME = timedelta(minutes=10)
MAX_RETAINED_SESSIONS = 200


class GameStatus(StrEnum):
    LOBBY = "LOBBY"
    COLLECTING = "COLLECTING"
    JUDGING = "JUDGING"
    LOCKED = "LOCKED"
    RESULTS = "RESULTS"
    CLOSED = "CLOSED"
    COMPLETED = "RESULTS"  # compatibility alias
    CANCELLED = "CLOSED"


class GameSessionError(Exception):
    """Expected invalid operation on a social game session."""


@dataclass(frozen=True, slots=True)
class AnonymousSubmission:
    submission_id: str
    answer: str


@dataclass(frozen=True, slots=True)
class RankedSubmission:
    submission_id: str
    score: int
    reason: str


@dataclass(frozen=True, slots=True)
class GameJudgement:
    """Validated best-to-worst Gemini ranking."""

    ranking: tuple[RankedSubmission, ...]
    winner_submission_id: str


@dataclass(frozen=True, slots=True)
class GamePublicSnapshot:
    session_id: str
    game_type: str
    status: GameStatus
    theme: str
    scenario: str
    host_user_id: int
    player_count: int
    submission_count: int
    max_players: int


@dataclass(slots=True)
class GameSession:
    session_id: str
    guild_id: int
    channel_id: int
    host_user_id: int
    game_type: str
    scenario: GameScenario
    status: GameStatus
    created_at: datetime
    expires_at: datetime
    participants: dict[int, str] = field(default_factory=dict)
    submissions: dict[str, str] = field(default_factory=dict)
    result: GameJudgement | None = None
    next_submission_number: int = 1
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def public_snapshot(self) -> GamePublicSnapshot:
        """Return public progress without submission text or ownership."""

        return GamePublicSnapshot(
            session_id=self.session_id,
            game_type=self.game_type,
            status=self.status,
            theme=self.scenario.theme,
            scenario=self.scenario.prompt,
            host_user_id=self.host_user_id,
            player_count=len(self.participants),
            submission_count=len(self.submissions),
            max_players=MAX_PLAYERS,
        )


class SocialGameService:
    """Own active game state and serialize every state transition."""

    def __init__(self, *, now: Callable[[], datetime] | None = None) -> None:
        self._sessions: dict[str, GameSession] = {}
        self._active_channels: dict[tuple[int, int], str] = {}
        self._registry_lock = asyncio.Lock()
        self._now = now or (lambda: datetime.now(UTC))

    async def create(
        self,
        *,
        guild_id: int,
        channel_id: int,
        host_user_id: int,
        game_type: str,
        scenario: GameScenario,
    ) -> GameSession:
        async with self._registry_lock:
            self._prune_finished_sessions()
            channel_key = (guild_id, channel_id)
            active_id = self._active_channels.get(channel_key)
            if active_id is not None:
                active = self._sessions.get(active_id)
                if active is not None and active.status not in {
                    GameStatus.COMPLETED,
                    GameStatus.CANCELLED,
                }:
                    raise GameSessionError("Another social game is already active in this channel.")

            now = self._now()
            session = GameSession(
                session_id=token_urlsafe(6),
                guild_id=guild_id,
                channel_id=channel_id,
                host_user_id=host_user_id,
                game_type=game_type,
                scenario=scenario,
                status=GameStatus.LOBBY,
                created_at=now,
                expires_at=now + LOBBY_LIFETIME,
            )
            session.participants[host_user_id] = "P1"
            session.next_submission_number = 2
            self._sessions[session.session_id] = session
            self._active_channels[channel_key] = session.session_id
            return session

    def _prune_finished_sessions(self) -> None:
        if len(self._sessions) < MAX_RETAINED_SESSIONS:
            return
        finished = sorted(
            (
                session
                for session in self._sessions.values()
                if session.status in {GameStatus.COMPLETED, GameStatus.CANCELLED}
            ),
            key=lambda session: session.created_at,
        )
        remove_count = len(self._sessions) - MAX_RETAINED_SESSIONS + 1
        for session in finished[:remove_count]:
            self._sessions.pop(session.session_id, None)

    def get(self, session_id: str) -> GameSession | None:
        return self._sessions.get(session_id)

    def active_in_channel(self, guild_id: int, channel_id: int) -> GameSession | None:
        """Return the currently active game for an end-game command."""

        session_id = self._active_channels.get((guild_id, channel_id))
        session = self._sessions.get(session_id) if session_id is not None else None
        if session is None or session.status in {GameStatus.COMPLETED, GameStatus.CANCELLED}:
            return None
        return session

    def active_count(self, guild_id: int) -> int:
        """Return active sessions belonging only to one server."""

        return sum(
            1
            for session in self._sessions.values()
            if session.guild_id == guild_id
            and session.status not in {GameStatus.COMPLETED, GameStatus.CANCELLED}
        )

    async def join(self, session_id: str, user_id: int) -> str:
        session = self._require(session_id)
        async with session.lock:
            self._expire_if_needed(session)
            self._require_status(session, GameStatus.LOBBY)
            if user_id in session.participants:
                raise GameSessionError("You already joined this game.")
            if len(session.participants) >= MAX_PLAYERS:
                raise GameSessionError("This game is full.")
            submission_id = f"P{session.next_submission_number}"
            session.next_submission_number += 1
            session.participants[user_id] = submission_id
            return submission_id

    async def leave(self, session_id: str, user_id: int) -> None:
        session = self._require(session_id)
        async with session.lock:
            self._expire_if_needed(session)
            self._require_status(session, GameStatus.LOBBY)
            if user_id == session.host_user_id:
                raise GameSessionError("The host must cancel the game instead.")
            if session.participants.pop(user_id, None) is None:
                raise GameSessionError("You are not in this game.")

    async def start(self, session_id: str, user_id: int) -> GamePublicSnapshot:
        session = self._require(session_id)
        async with session.lock:
            self._expire_if_needed(session)
            self._require_host(session, user_id)
            self._require_status(session, GameStatus.LOBBY)
            if len(session.participants) < MIN_PLAYERS:
                raise GameSessionError(f"At least {MIN_PLAYERS} players are required.")
            self._transition(session, GameStatus.COLLECTING)
            session.expires_at = self._now() + COLLECTION_LIFETIME
            return session.public_snapshot()

    async def submit(self, session_id: str, user_id: int, answer: str) -> GamePublicSnapshot:
        session = self._require(session_id)
        clean_answer = " ".join(answer.split()).strip()
        if not clean_answer:
            raise GameSessionError("Your submission cannot be empty.")
        if len(clean_answer) > MAX_SUBMISSION_LENGTH:
            raise GameSessionError(
                f"Submissions can be at most {MAX_SUBMISSION_LENGTH} characters."
            )

        async with session.lock:
            self._expire_if_needed(session)
            self._require_status(session, GameStatus.COLLECTING)
            if self._now() >= session.expires_at:
                raise GameSessionError(
                    "Submissions are closed; waiting for the submitted answers to be judged."
                )
            submission_id = session.participants.get(user_id)
            if submission_id is None:
                raise GameSessionError("You are not a participant in this game.")
            if submission_id in session.submissions:
                raise GameSessionError("You already submitted an answer.")
            if clean_answer.casefold() in {
                value.casefold() for value in session.submissions.values()
            }:
                raise GameSessionError("That answer was already submitted. Choose something else.")
            session.submissions[submission_id] = clean_answer
            return session.public_snapshot()

    async def claim_judging(
        self,
        session_id: str,
        user_id: int | None = None,
        *,
        force: bool = False,
        timed_out: bool = False,
    ) -> tuple[AnonymousSubmission, ...]:
        session = self._require(session_id)
        async with session.lock:
            if timed_out and self._now() < session.expires_at:
                raise GameSessionError("The submission round is still active.")
            if not timed_out:
                self._expire_if_needed(session)
            if session.status not in {GameStatus.COLLECTING, GameStatus.LOCKED}:
                raise GameSessionError("This game is not accepting that action.")
            if force:
                if user_id is None:
                    raise GameSessionError("A host is required to judge early.")
                self._require_host(session, user_id)
            elif (
                session.status is GameStatus.COLLECTING
                and not timed_out
                and len(session.submissions) != len(session.participants)
            ):
                raise GameSessionError("Not everyone has submitted yet.")
            if len(session.submissions) < MIN_PLAYERS:
                raise GameSessionError(f"At least {MIN_PLAYERS} submissions are required.")

            if session.status is GameStatus.COLLECTING:
                self._transition(session, GameStatus.LOCKED)
            self._transition(session, GameStatus.JUDGING)
            return tuple(
                AnonymousSubmission(submission_id=submission_id, answer=answer)
                for submission_id, answer in session.submissions.items()
            )

    async def complete(self, session_id: str, result: GameJudgement) -> None:
        session = self._require(session_id)
        async with session.lock:
            self._require_status(session, GameStatus.JUDGING)
            expected = set(session.submissions)
            returned = {entry.submission_id for entry in result.ranking}
            if expected != returned:
                raise GameSessionError("The accepted result does not match this session.")
            # Revalidate even if a caller bypassed the model-response parser.
            parse_game_judgement(
                json.dumps(
                    {
                        "ranking": [
                            {
                                "submission_id": entry.submission_id,
                                "score": entry.score,
                                "reason": entry.reason,
                            }
                            for entry in result.ranking
                        ],
                        "winner": result.winner_submission_id,
                    }
                ),
                expected,
            )
            session.result = result
            self._transition(session, GameStatus.RESULTS)
            self._active_channels.pop((session.guild_id, session.channel_id), None)

    async def judging_failed(self, session_id: str) -> None:
        session = self._require(session_id)
        async with session.lock:
            if session.status is GameStatus.JUDGING:
                self._transition(session, GameStatus.LOCKED)
                session.expires_at = self._now() + COLLECTION_LIFETIME

    async def cancel(
        self,
        session_id: str,
        user_id: int | None = None,
        *,
        expected_status: GameStatus | None = None,
    ) -> None:
        session = self._require(session_id)
        async with session.lock:
            if expected_status is not None:
                self._require_status(session, expected_status)
            if user_id is not None:
                self._require_host(session, user_id)
            if session.status in {GameStatus.COMPLETED, GameStatus.CANCELLED}:
                raise GameSessionError("This game is already over.")
            self._transition(session, GameStatus.CLOSED)
            self._active_channels.pop((session.guild_id, session.channel_id), None)

    async def expire_abandoned(self, session_id: str) -> bool:
        session = self._require(session_id)
        async with session.lock:
            if session.status not in {GameStatus.LOBBY, GameStatus.COLLECTING, GameStatus.LOCKED}:
                return False
            if self._now() < session.expires_at:
                return False
            self._transition(session, GameStatus.CLOSED)
            self._active_channels.pop((session.guild_id, session.channel_id), None)
            return True

    async def close(self, session_id: str) -> None:
        session = self._require(session_id)
        async with session.lock:
            self._require_status(session, GameStatus.RESULTS)
            self._transition(session, GameStatus.CLOSED)

    @staticmethod
    def _transition(session: GameSession, target: GameStatus) -> None:
        try:
            validate_transition(session.status, target)
        except ValueError as exc:
            raise GameSessionError(str(exc)) from exc
        previous = session.status
        session.status = target
        event(
            "game_transition",
            feature=session.game_type,
            guild_id=session.guild_id,
            channel_id=session.channel_id,
            session_id=session.session_id,
            previous=previous,
            phase=target,
        )

    def owner_for_submission(self, session_id: str, submission_id: str) -> int:
        """Map a validated anonymous ID back to Discord state after judging."""

        session = self._require(session_id)
        for user_id, candidate_id in session.participants.items():
            if candidate_id == submission_id:
                return user_id
        raise GameSessionError("Unknown submission identifier.")

    def _require(self, session_id: str) -> GameSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise GameSessionError("This game no longer exists.")
        return session

    def _expire_if_needed(self, session: GameSession) -> None:
        if (
            session.status in {GameStatus.LOBBY, GameStatus.LOCKED}
            and self._now() >= session.expires_at
        ):
            self._transition(session, GameStatus.CLOSED)
            self._active_channels.pop((session.guild_id, session.channel_id), None)
            raise GameSessionError("This game expired.")

    @staticmethod
    def _require_status(session: GameSession, status: GameStatus) -> None:
        if session.status is not status:
            raise GameSessionError(f"This game is not accepting that action ({session.status}).")

    @staticmethod
    def _require_host(session: GameSession, user_id: int) -> None:
        if session.host_user_id != user_id:
            raise GameSessionError("Only the game host can do that.")


def parse_game_judgement(raw: str, expected_ids: set[str]) -> GameJudgement:
    """Parse and strictly validate a best-to-worst anonymous ranking."""

    payload = _load_json_object(raw)
    ranking = payload.get("ranking")
    winner = payload.get("winner")
    if not isinstance(ranking, list) or not isinstance(winner, str):
        raise ValueError("Judgement must contain ranking and winner.")

    entries: list[RankedSubmission] = []
    seen: set[str] = set()
    for item in ranking:
        if not isinstance(item, dict):
            raise ValueError("Every ranking entry must be an object.")
        submission_id = item.get("submission_id")
        score = item.get("score")
        reason = item.get("reason")
        if not isinstance(submission_id, str) or submission_id not in expected_ids:
            raise ValueError("Unknown submission ID in ranking.")
        if submission_id in seen:
            raise ValueError("Duplicate submission ID in ranking.")
        if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
            raise ValueError("Ranking scores must be integers from 0 to 100.")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Every ranking entry needs a reason.")
        if DISCORD_MENTION_PATTERN.search(reason):
            raise ValueError("Gemini must not invent Discord mentions.")
        seen.add(submission_id)
        entries.append(RankedSubmission(submission_id, score, " ".join(reason.split())[:300]))

    if seen != expected_ids or len(entries) != len(expected_ids):
        raise ValueError("Every submission must appear exactly once.")
    if winner not in expected_ids or not entries or entries[0].submission_id != winner:
        raise ValueError("Winner must be the first ranked submission.")
    if any(entries[index].score < entries[index + 1].score for index in range(len(entries) - 1)):
        raise ValueError("Ranking must be ordered from highest score to lowest.")
    return GameJudgement(tuple(entries), winner)


class SocialGameJudge:
    """Ask Gemini to compare all anonymous submissions in one request."""

    def __init__(self, llm: LLMProvider | None) -> None:
        self.llm = llm

    async def judge(
        self,
        *,
        game_type: str,
        scenario: GameScenario,
        submissions: tuple[AnonymousSubmission, ...],
    ) -> GameJudgement | None:
        if self.llm is None:
            return None
        expected_ids = {submission.submission_id for submission in submissions}
        entries = [
            {"submission_id": submission.submission_id, "answer": submission.answer}
            for submission in submissions
        ]
        system, scoring, schema = build_game_instructions(game_type)
        prompt = (
            f"Game: {game_type}\nTheme: {scenario.theme}\nScenario: {scenario.prompt}\n"
            f"Judge by: {scoring}. Keep each punchy reason under 22 words.\n"
            f"Anonymous submissions: {json.dumps(entries, ensure_ascii=False)}"
        )
        correction_prompt = (
            prompt + "\nYour previous result was invalid. Return only corrected JSON using exactly "
            f"these IDs: {sorted(expected_ids)}. Required shape: {schema}"
        )

        for attempt in range(2):
            reply = await self.llm.generate_json(
                system,
                prompt if attempt == 0 else correction_prompt,
                max_output_tokens=900,
                timeout_seconds=15,
            )
            if reply is None:
                continue
            try:
                return parse_game_judgement(json.dumps(reply), expected_ids)
            except ValueError:
                event("llm_fallback", reason="invalid_judgement", attempt=attempt + 1)
                logger.warning(
                    "Gemini returned invalid social game judgement attempt=%s", attempt + 1
                )
        return None


def _load_json_object(raw: str) -> dict:
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    payload = json.loads(cleaned)
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object.")
    return payload
