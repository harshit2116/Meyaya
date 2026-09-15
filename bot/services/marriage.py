"""Marriage business logic."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import time

from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.marriage import Marriage
from bot.repositories.marriages import MarriageRepository


class AlreadyMarriedError(Exception):
    """Raised when a user involved in a proposal is already married."""

    def __init__(self, user_id: int) -> None:
        self.user_id = user_id
        super().__init__(f"User {user_id} is already married.")


class NotMarriedError(Exception):
    """Raised when a user tries to divorce without an active marriage."""


class StaleMarriageConfirmationError(Exception):
    """Raised when a divorce button no longer identifies the active marriage."""


class PendingProposalError(Exception):
    """Raised when either member already has a pending proposal."""


@dataclass(frozen=True, slots=True)
class MarriageResult:
    marriage_id: int
    user_a_id: int
    user_b_id: int
    married_at: datetime


@dataclass(frozen=True, slots=True)
class MarriageSummary:
    marriage_id: int
    user_id: int
    partner_id: int
    married_at: datetime
    days_together: int
    next_anniversary: datetime
    days_until_anniversary: int


class PendingProposalRegistry:
    """Prevent overlapping proposals from involving the same member."""

    def __init__(self) -> None:
        self._by_user: dict[int, tuple[tuple[int, int], float]] = {}
        self._lock = asyncio.Lock()

    async def reserve(self, proposer_id: int, target_id: int) -> None:
        pair = (proposer_id, target_id)
        async with self._lock:
            self._prune()
            if proposer_id in self._by_user or target_id in self._by_user:
                raise PendingProposalError(
                    "One of you already has a proposal waiting for an answer."
                )
            entry = (pair, time.monotonic() + 300)
            self._by_user[proposer_id] = entry
            self._by_user[target_id] = entry

    async def release(self, proposer_id: int, target_id: int) -> None:
        pair = (proposer_id, target_id)
        async with self._lock:
            proposer_entry = self._by_user.get(proposer_id)
            target_entry = self._by_user.get(target_id)
            if proposer_entry is not None and proposer_entry[0] == pair:
                self._by_user.pop(proposer_id, None)
            if target_entry is not None and target_entry[0] == pair:
                self._by_user.pop(target_id, None)

    async def is_pending(self, user_id: int) -> bool:
        async with self._lock:
            self._prune()
            return user_id in self._by_user

    def _prune(self) -> None:
        now = time.monotonic()
        expired = [user_id for user_id, (_, expiry) in self._by_user.items() if expiry <= now]
        for user_id in expired:
            self._by_user.pop(user_id, None)


_MARRIAGE_WRITE_LOCK = asyncio.Lock()


class MarriageService:
    """Handles marriage and divorce logic."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.marriages = MarriageRepository(session)

    async def get_active_marriage(self, user_id: int) -> Marriage | None:
        """Return the caller's active marriage row, if any."""

        return await self.marriages.get_active_for_user(user_id)

    async def married_user_ids(self, *user_ids: int) -> set[int]:
        """Return which requested members are married using one database query."""

        requested = set(user_ids)
        records = await self.marriages.get_active_for_users(requested)
        occupied: set[int] = set()
        for record in records:
            if record.user_a_id in requested:
                occupied.add(record.user_a_id)
            if record.user_b_id in requested:
                occupied.add(record.user_b_id)
        return occupied

    async def get_summary(
        self,
        user_id: int,
        *,
        now: datetime | None = None,
    ) -> MarriageSummary | None:
        """Return duration and anniversary information for one married member."""

        record = await self.marriages.get_active_for_user(user_id)
        if record is None:
            return None
        return self.summary_from_record(record, user_id, now=now)

    @classmethod
    def summary_from_record(
        cls,
        record: Marriage,
        user_id: int,
        *,
        now: datetime | None = None,
    ) -> MarriageSummary:
        """Build a summary from an already-loaded record without another query."""

        current = now or datetime.now(UTC)
        married_at = cls._as_aware(record.married_at)
        partner_id = record.user_b_id if record.user_a_id == user_id else record.user_a_id
        anniversary = cls._next_anniversary(married_at, current)
        return MarriageSummary(
            marriage_id=record.id,
            user_id=user_id,
            partner_id=partner_id,
            married_at=married_at,
            days_together=max(0, (current.date() - married_at.date()).days),
            next_anniversary=anniversary,
            days_until_anniversary=max(0, (anniversary.date() - current.date()).days),
        )

    async def marry(self, proposer_id: int, target_id: int) -> MarriageResult:
        """Create a marriage after acceptance. Raises AlreadyMarriedError if either is taken."""

        async with _MARRIAGE_WRITE_LOCK:
            if proposer_id == target_id:
                raise ValueError("A user cannot marry themselves.")

            occupied = await self.married_user_ids(proposer_id, target_id)
            if proposer_id in occupied:
                raise AlreadyMarriedError(proposer_id)
            if target_id in occupied:
                raise AlreadyMarriedError(target_id)

            record = await self.marriages.create(proposer_id, target_id)
            await self.session.commit()
            return MarriageResult(
                marriage_id=record.id,
                user_a_id=record.user_a_id,
                user_b_id=record.user_b_id,
                married_at=self._as_aware(record.married_at),
            )

    async def divorce(
        self,
        user_id: int,
        *,
        marriage_id: int,
        partner_id: int,
    ) -> MarriageResult:
        """Dissolve only the exact marriage approved by the confirmation view."""

        async with _MARRIAGE_WRITE_LOCK:
            record = await self.marriages.get_exact_for_divorce(
                marriage_id,
                user_id,
                partner_id,
            )
            if record is None:
                raise StaleMarriageConfirmationError(
                    "This divorce confirmation is no longer valid."
                )

            result = MarriageResult(
                marriage_id=record.id,
                user_a_id=record.user_a_id,
                user_b_id=record.user_b_id,
                married_at=self._as_aware(record.married_at),
            )
            await self.marriages.delete(record)
            await self.session.commit()
            return result

    @staticmethod
    def _as_aware(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @staticmethod
    def _next_anniversary(married_at: datetime, current: datetime) -> datetime:
        married_at = MarriageService._as_aware(married_at)
        current = MarriageService._as_aware(current)
        year = current.year
        try:
            anniversary = married_at.replace(year=year)
        except ValueError:
            anniversary = married_at.replace(year=year, day=28)
        if anniversary.date() < current.date():
            year += 1
            try:
                anniversary = married_at.replace(year=year)
            except ValueError:
                anniversary = married_at.replace(year=year, day=28)
        return anniversary
