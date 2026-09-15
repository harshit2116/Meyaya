"""Persistent court workflow and safe structured Gemini judging."""

from __future__ import annotations

from bot.prompts.court import build_court_instructions

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
import json
import logging
import re
from weakref import WeakValueDictionary

from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.court import CourtCase
from bot.repositories.court import CourtRepository
from bot.services.llm import LLMProvider
from bot.services.game_engine import validate_transition
from bot.logging.telemetry import event
from bot.services.social_games import _load_json_object

logger = logging.getLogger(__name__)

_COURT_CASE_LOCKS: WeakValueDictionary[int, asyncio.Lock] = WeakValueDictionary()

MAX_CHARGE_LENGTH = 500
MAX_STATEMENT_LENGTH = 1200
MAX_WITNESSES = 5
FORBIDDEN_PUNISHMENT = re.compile(
    r"\b(?:ban|kick|mute|timeout|time[ -]?out|remove\s+(?:a\s+)?role|delete\s+messages?|moderation)\b",
    re.IGNORECASE,
)


class CourtStatus(StrEnum):
    LOBBY = "LOBBY"
    PENDING = "LOBBY"
    COLLECTING = "COLLECTING"
    JUDGING = "JUDGING"
    CLARIFYING = "CLARIFYING"
    LOCKED = "LOCKED"
    RESULTS = "RESULTS"
    CLOSED = "CLOSED"
    COMPLETED = "RESULTS"
    DECLINED = "CLOSED"

    @classmethod
    def _missing_(cls, value):
        return {"PENDING": cls.LOBBY, "COMPLETED": cls.RESULTS, "DECLINED": cls.CLOSED}.get(value)


class CourtVerdict(StrEnum):
    GUILTY = "guilty"
    NOT_GUILTY = "not_guilty"
    MIXED = "mixed"


class CourtError(Exception):
    """Expected invalid court operation."""


def court_case_lock(case_id: int) -> asyncio.Lock:
    """Return the process-local lock shared by all callbacks for one case."""

    return _COURT_CASE_LOCKS.setdefault(case_id, asyncio.Lock())


@dataclass(frozen=True, slots=True)
class CourtEvidence:
    case_id: int
    charge: str
    plaintiff_statement: str
    defendant_statement: str
    witness_statements: tuple[tuple[int, str], ...]
    clarification_question: str | None
    clarification_answers: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class CourtJudgement:
    verdict: CourtVerdict
    plaintiff_summary: str
    defendant_summary: str
    reasoning: str
    decisive_factors: str
    punishment: str | None


@dataclass(frozen=True, slots=True)
class CourtClarification:
    """One targeted follow-up requested before Gemini reaches a verdict."""

    question: str
    target: str


def court_channel_error(configured_channel_id: int | None, current_channel_id: int) -> str | None:
    """Return a safe redirect/configuration message when Court is unavailable here."""

    if configured_channel_id is None:
        return "Court is not configured yet. A server manager can use `/setcourt` here."
    if configured_channel_id != current_channel_id:
        return f"Court cases must be filed in <#{configured_channel_id}>."
    return None


class CourtService:
    """Manage case state without granting any moderation capability."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.cases = CourtRepository(session)

    async def configured_channel(
        self,
        guild_id: int,
        legacy_fallback: int | None = None,
    ) -> int | None:
        """Resolve database configuration before the legacy environment fallback."""

        configuration = await self.cases.get_configuration(guild_id)
        if configuration is None:
            return legacy_fallback
        return configuration.channel_id

    async def set_channel(
        self,
        guild_id: int,
        channel_id: int,
        updated_by_user_id: int,
    ) -> None:
        await self.cases.set_channel(guild_id, channel_id, updated_by_user_id)
        await self.session.commit()

    async def remove_channel(self, guild_id: int, updated_by_user_id: int) -> None:
        """Store an explicit disabled value so an old env fallback stays disabled."""

        await self.cases.set_channel(guild_id, None, updated_by_user_id)
        await self.session.commit()

    async def create_case(
        self,
        *,
        guild_id: int,
        channel_id: int,
        plaintiff_id: int,
        defendant_id: int,
        charge: str,
    ) -> CourtCase:
        clean_charge = self._clean(charge, MAX_CHARGE_LENGTH)
        if plaintiff_id == defendant_id:
            raise CourtError("You cannot take yourself to court.")
        if not clean_charge:
            raise CourtError("A charge or reason is required.")
        case = await self.cases.create(
            guild_id=guild_id,
            channel_id=channel_id,
            plaintiff_id=plaintiff_id,
            defendant_id=defendant_id,
            charge=clean_charge,
        )
        await self.session.commit()
        return case

    async def get_case(self, case_id: int) -> CourtCase:
        case = await self.cases.get(case_id)
        if case is None:
            raise CourtError("That court case no longer exists.")
        case.status = CourtStatus(case.status)
        return case

    async def accept(self, case_id: int, user_id: int) -> CourtCase:
        case = await self.get_case(case_id)
        self._require_status(case, CourtStatus.PENDING)
        if case.defendant_id != user_id:
            raise CourtError("Only the defendant can accept this case.")
        self._transition(case, CourtStatus.COLLECTING)
        await self.session.commit()
        return case

    async def register_witness(self, case_id: int, user_id: int) -> CourtCase:
        """Register during the invitation stage before evidence collection begins."""

        case = await self.get_case(case_id)
        self._require_status(case, CourtStatus.PENDING)
        if user_id in {case.plaintiff_id, case.defendant_id}:
            raise CourtError("The plaintiff and defendant cannot register as witnesses.")
        registered = list(case.registered_witness_ids or [])
        if user_id in registered:
            raise CourtError("You are already registered as a witness.")
        if len(registered) >= MAX_WITNESSES:
            raise CourtError("This case already has the maximum number of witnesses.")
        registered.append(user_id)
        case.registered_witness_ids = registered
        await self.session.commit()
        return case

    async def decline(self, case_id: int, user_id: int) -> CourtCase:
        case = await self.get_case(case_id)
        self._require_status(case, CourtStatus.PENDING)
        if case.defendant_id != user_id:
            raise CourtError("Only the defendant can decline this case.")
        self._transition(case, CourtStatus.CLOSED)
        await self.session.commit()
        return case

    async def submit_statement(self, case_id: int, user_id: int, statement: str) -> CourtCase:
        case = await self.get_case(case_id)
        self._require_status(case, CourtStatus.COLLECTING)
        clean = self._clean(statement, MAX_STATEMENT_LENGTH)
        if not clean:
            raise CourtError("A statement cannot be empty.")
        if user_id == case.plaintiff_id:
            case.plaintiff_statement = clean
        elif user_id == case.defendant_id:
            case.defendant_statement = clean
        else:
            raise CourtError("Only the plaintiff or defendant can use this statement button.")
        await self.session.commit()
        return case

    async def submit_witness(self, case_id: int, user_id: int, statement: str) -> CourtCase:
        case = await self.get_case(case_id)
        self._require_status(case, CourtStatus.COLLECTING)
        if user_id in {case.plaintiff_id, case.defendant_id}:
            raise CourtError("The plaintiff and defendant must use their own statement buttons.")
        if user_id not in set(case.registered_witness_ids or []):
            raise CourtError("Only witnesses registered before the case started may testify.")
        clean = self._clean(statement, MAX_STATEMENT_LENGTH)
        if not clean:
            raise CourtError("A witness statement cannot be empty.")
        witnesses = dict(case.witness_statements or {})
        key = str(user_id)
        witnesses[key] = clean
        case.witness_statements = witnesses
        await self.session.commit()
        return case

    async def claim_judging(
        self,
        case_id: int,
        user_id: int,
        *,
        automatic: bool = False,
    ) -> CourtEvidence:
        case = await self.get_case(case_id)
        if case.status not in {CourtStatus.COLLECTING, CourtStatus.CLARIFYING, CourtStatus.LOCKED}:
            raise CourtError(f"This case is not accepting that action ({case.status}).")
        if automatic:
            if user_id not in {case.plaintiff_id, case.defendant_id}:
                raise CourtError("Only a case participant can trigger automatic judging.")
            if case.registered_witness_ids:
                raise CourtError("Automatic judging only starts when no witnesses are registered.")
        if not automatic and case.plaintiff_id != user_id:
            raise CourtError("Only the plaintiff can lock statements and request a verdict.")
        if not case.plaintiff_statement or not case.defendant_statement:
            raise CourtError("Both the plaintiff and defendant must submit statements first.")
        if case.status == CourtStatus.CLARIFYING:
            self._require_clarification_answers(case)
        if case.status != CourtStatus.LOCKED:
            self._transition(case, CourtStatus.LOCKED)
        self._transition(case, CourtStatus.JUDGING)
        await self.session.commit()
        registered = {str(witness_id) for witness_id in (case.registered_witness_ids or [])}
        return CourtEvidence(
            case_id=case.id,
            charge=case.charge,
            plaintiff_statement=case.plaintiff_statement,
            defendant_statement=case.defendant_statement,
            witness_statements=tuple(
                (int(user_id_text), text)
                for user_id_text, text in (case.witness_statements or {}).items()
                if user_id_text in registered
            ),
            clarification_question=case.clarification_question,
            clarification_answers=tuple((case.clarification_answers or {}).items()),
        )

    async def request_clarification(
        self,
        case_id: int,
        clarification: CourtClarification,
    ) -> CourtCase:
        case = await self.get_case(case_id)
        self._require_status(case, CourtStatus.JUDGING)
        if case.clarification_question:
            raise CourtError("This case has already used its clarification round.")
        question = self._clean(clarification.question, 500)
        if not question or clarification.target not in {"plaintiff", "defendant", "both"}:
            raise CourtError("Gemini returned an invalid clarification request.")
        case.clarification_question = question
        case.clarification_target = clarification.target
        case.clarification_answers = {}
        self._transition(case, CourtStatus.CLARIFYING)
        await self.session.commit()
        return case

    async def submit_clarification(
        self,
        case_id: int,
        user_id: int,
        answer: str,
    ) -> CourtCase:
        case = await self.get_case(case_id)
        self._require_status(case, CourtStatus.CLARIFYING)
        role = self._party_role(case, user_id)
        if role is None:
            raise CourtError("Only the plaintiff or defendant can answer this follow-up.")
        if case.clarification_target not in {role, "both"}:
            raise CourtError(f"This follow-up question is for the {case.clarification_target}.")
        clean = self._clean(answer, MAX_STATEMENT_LENGTH)
        if not clean:
            raise CourtError("A clarification answer cannot be empty.")
        answers = dict(case.clarification_answers or {})
        answers[role] = clean
        case.clarification_answers = answers
        await self.session.commit()
        return case

    async def judging_failed(self, case_id: int) -> CourtCase:
        case = await self.get_case(case_id)
        if case.status == CourtStatus.JUDGING:
            self._transition(case, CourtStatus.LOCKED)
            await self.session.commit()
        return case

    async def complete(self, case_id: int, judgement: CourtJudgement) -> CourtCase:
        case = await self.get_case(case_id)
        self._require_status(case, CourtStatus.JUDGING)
        case.verdict = judgement.verdict
        case.plaintiff_summary = judgement.plaintiff_summary
        case.defendant_summary = judgement.defendant_summary
        case.reasoning = judgement.reasoning
        case.decisive_factors = judgement.decisive_factors
        case.punishment = safe_entertainment_punishment(judgement.punishment)
        self._transition(case, CourtStatus.RESULTS)
        case.completed_at = datetime.now(UTC)
        await self.session.commit()
        return case

    async def close(self, case_id: int) -> CourtCase:
        case = await self.get_case(case_id)
        self._require_status(case, CourtStatus.RESULTS)
        self._transition(case, CourtStatus.CLOSED)
        await self.session.commit()
        return case

    async def expire(self, case_id: int, expected: tuple[CourtStatus, ...]) -> CourtCase:
        """A stale view cannot close a case that advanced to another phase."""
        case = await self.get_case(case_id)
        if case.status not in expected:
            raise CourtError("The case has already advanced.")
        self._transition(case, CourtStatus.CLOSED)
        case.completed_at = datetime.now(UTC)
        await self.session.commit()
        return case

    @staticmethod
    def _transition(case: CourtCase, target: CourtStatus) -> None:
        try:
            validate_transition(case.status, target, court=True)
        except ValueError as exc:
            raise CourtError(str(exc)) from exc
        previous = case.status
        case.status = target
        event("game_transition", feature="court", guild_id=getattr(case, "guild_id", None),
              channel_id=getattr(case, "channel_id", None), case_id=case.id,
              previous=previous, phase=target)

    @staticmethod
    def _party_role(case: CourtCase, user_id: int) -> str | None:
        if user_id == case.plaintiff_id:
            return "plaintiff"
        if user_id == case.defendant_id:
            return "defendant"
        return None

    @staticmethod
    def _require_clarification_answers(case: CourtCase) -> None:
        answers = case.clarification_answers or {}
        target = case.clarification_target
        required = {"plaintiff", "defendant"} if target == "both" else {target}
        if None in required or not required.issubset(answers):
            missing = " and ".join(sorted(str(role) for role in required if role not in answers))
            raise CourtError(f"Waiting for the {missing} clarification answer.")

    @staticmethod
    def _require_status(case: CourtCase, expected: CourtStatus) -> None:
        if case.status != expected:
            raise CourtError(f"This case is not accepting that action ({case.status}).")

    @staticmethod
    def _clean(value: str, limit: int) -> str:
        return " ".join(value.split())[:limit]


def safe_entertainment_punishment(punishment: str | None) -> str | None:
    """Reject moderation-like punishments; application code never executes verdict text."""

    if punishment is None:
        return None
    clean = " ".join(punishment.split())[:300]
    if not clean:
        return None
    if FORBIDDEN_PUNISHMENT.search(clean):
        return "Sentenced to one dramatic apology and absolutely no real moderation action."
    return clean


def parse_court_decision(raw: str) -> CourtJudgement | CourtClarification:
    """Parse either a complete verdict or one bounded clarification request."""

    payload = _load_json_object(raw)
    outcome = payload.get("outcome")
    if outcome == "clarification":
        question = payload.get("question")
        target = payload.get("target")
        if not isinstance(question, str) or not question.strip():
            raise ValueError("A clarification requires one question.")
        if target not in {"plaintiff", "defendant", "both"}:
            raise ValueError("A clarification target must be plaintiff, defendant, or both.")
        return CourtClarification(
            question=" ".join(question.split())[:500],
            target=target,
        )

    raw_verdict = payload.get("verdict")
    plaintiff_summary = payload.get("plaintiff_summary")
    defendant_summary = payload.get("defendant_summary")
    reasoning = payload.get("reasoning")
    decisive_factors = payload.get("decisive_factors")
    punishment = payload.get("punishment")
    required_text = (plaintiff_summary, defendant_summary, reasoning, decisive_factors)
    if not isinstance(raw_verdict, str) or any(
        not isinstance(value, str) or not value.strip() for value in required_text
    ):
        raise ValueError("Court verdict requires both summaries, reasoning, and decisive factors.")
    normalized = raw_verdict.strip().casefold().replace(" ", "_").replace("-", "_")
    try:
        verdict = CourtVerdict(normalized)
    except ValueError as exc:
        raise ValueError("Unknown court verdict.") from exc
    if punishment is not None and not isinstance(punishment, str):
        raise ValueError("Punishment must be text or null.")
    return CourtJudgement(
        verdict=verdict,
        plaintiff_summary=" ".join(plaintiff_summary.split())[:500],
        defendant_summary=" ".join(defendant_summary.split())[:500],
        reasoning=" ".join(reasoning.split())[:600],
        decisive_factors=" ".join(decisive_factors.split())[:500],
        punishment=safe_entertainment_punishment(punishment),
    )


def parse_court_judgement(raw: str) -> CourtJudgement:
    """Backward-compatible verdict-only parser used by safety tests and callers."""

    decision = parse_court_decision(raw)
    if isinstance(decision, CourtClarification):
        raise ValueError("Expected a verdict, not a clarification request.")
    return decision


class CourtJudge:
    """Use Gemini only for a structured entertainment verdict."""

    def __init__(self, llm: LLMProvider | None) -> None:
        self.llm = llm

    async def judge(self, evidence: CourtEvidence) -> CourtJudgement | CourtClarification | None:
        if self.llm is None:
            return None
        witnesses = [
            {"witness_id": f"W{index}", "statement": statement}
            for index, (_, statement) in enumerate(evidence.witness_statements, start=1)
        ]
        can_clarify = evidence.clarification_question is None
        system, verdict_schema, clarification_schema = build_court_instructions(can_clarify)
        evidence_payload = {
            "charge": evidence.charge,
            "plaintiff_statement": evidence.plaintiff_statement,
            "defendant_statement": evidence.defendant_statement,
            "witnesses": witnesses,
            "clarification_question": evidence.clarification_question,
            "clarification_answers": dict(evidence.clarification_answers),
        }
        prompt = "Judge this case using only the supplied evidence: " + json.dumps(
            evidence_payload, ensure_ascii=False
        )
        correction_prompt = (
            prompt
            + "\nYour previous result was invalid. Return corrected JSON only using one allowed "
            f"shape. Verdict: {verdict_schema}. Clarification: {clarification_schema}."
        )
        for attempt in range(2):
            reply = await self.llm.generate_json(
                system,
                prompt if attempt == 0 else correction_prompt,
                max_output_tokens=500,
                timeout_seconds=15,
            )
            if reply is None:
                continue
            try:
                decision = parse_court_decision(json.dumps(reply))
                if not can_clarify and isinstance(decision, CourtClarification):
                    raise ValueError("A second clarification round is not allowed.")
                return decision
            except ValueError:
                event("llm_fallback", reason="invalid_judgement", attempt=attempt + 1)
                logger.warning("Gemini returned invalid court judgement attempt=%s", attempt + 1)
        return None
