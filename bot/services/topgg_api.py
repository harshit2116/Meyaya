"""Bounded, read-only Top.gg v1 verification using a project-scoped token."""

import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import aiohttp

from bot.services.topgg_votes import VOTE_LIFETIME, InvalidVote, VerifiedVote, event_time

logger = logging.getLogger(__name__)
API_ROOT = "https://top.gg/api/v1/projects/@me"
MAX_RESPONSE_BYTES = 32768


class TopggUnavailable(Exception):
    """Safe message for a verification failure; never include provider content."""


class TopggCursorExpired(TopggUnavailable):
    """Restart the current history window when a saved cursor is no longer valid."""


@dataclass(frozen=True)
class VotePage:
    votes: tuple[VerifiedVote, ...]
    cursor: str | None
    complete: bool


def parse_vote_page(payload, bot_id: int, *, now=None) -> VotePage:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise InvalidVote("Invalid vote page")
    records = payload["data"]
    if len(records) > 200:
        raise InvalidVote("Vote page too large")
    if not records:
        return VotePage((), None, True)
    cursor = payload.get("cursor")
    if not isinstance(cursor, str) or not 1 <= len(cursor) <= 2048:
        raise InvalidVote("Missing pagination cursor")
    votes = []
    now = now or datetime.now(UTC)
    for record in records:
        if not isinstance(record, dict):
            raise InvalidVote("Invalid vote record")
        identity = record.get("platform_id")
        if (
            not isinstance(identity, str)
            or not identity.isascii()
            or not identity.isdecimal()
            or not 1 <= len(identity) <= 19
            or not 0 < int(identity) < 2**63
        ):
            raise InvalidVote("Invalid Discord voter ID")
        vote = parse_vote_status(record, bot_id, int(identity), now=now)
        if vote is not None:
            votes.append(vote)
    return VotePage(tuple(votes), cursor, False)


def parse_vote_status(payload, bot_id: int, user_id: int, *, now=None) -> VerifiedVote | None:
    now = now or datetime.now(UTC)
    if not isinstance(payload, dict):
        raise InvalidVote("Invalid vote status")
    voted_at = event_time(payload.get("created_at"))
    provider_expiry = event_time(payload.get("expires_at"))
    if voted_at > now or provider_expiry <= voted_at:
        raise InvalidVote("Invalid vote interval")
    expires_at = voted_at + VOTE_LIFETIME
    if min(provider_expiry, expires_at) <= now:
        return None
    # The status API has no vote ID. A canonical timestamp plus the Discord
    # identities gives a stable receipt, and the DB also uniquely constrains
    # (user_id, voted_at). Rechecking never refills an existing reward.
    receipt = hashlib.sha256(
        f"{bot_id}:{user_id}:{voted_at.isoformat(timespec='microseconds')}".encode()
    ).hexdigest()
    return VerifiedVote(receipt, user_id, voted_at, expires_at)


class TopggAPI:
    def __init__(self, http_session, token: str, project_id: str):
        self.http = http_session
        self._token = token.strip()
        self.project_id = project_id
        self._verified_bot = None
        self._identity_lock = asyncio.Lock()
        self._request_lock = asyncio.Lock()
        self._requests = deque()
        self._blocked_until = 0.0
        self._cache = OrderedDict()

    async def _reserve_request(self):
        async with self._request_lock:
            now = time.monotonic()
            if now < self._blocked_until:
                raise TopggUnavailable(
                    "Top.gg verification is temporarily unavailable. Please try again later."
                )
            while self._requests and self._requests[0] <= now - 60:
                self._requests.popleft()
            # Stay conservatively below the stricter published bot-route cap.
            if len(self._requests) >= 45:
                raise TopggUnavailable("Vote verification is busy. Please try again in a minute.")
            self._requests.append(now)

    @staticmethod
    async def _read_json(response):
        body = bytearray()
        async for chunk in response.content.iter_chunked(4096):
            body.extend(chunk)
            if len(body) > MAX_RESPONSE_BYTES:
                raise TopggUnavailable(
                    "Top.gg returned an unreadable response. Please try again later."
                )
        try:
            return json.loads(body)
        except (ValueError, UnicodeError):
            raise TopggUnavailable(
                "Top.gg returned an unreadable response. Please try again later."
            ) from None

    def _backoff(self, response, payload):
        delays = [3600.0]
        header = response.headers.get("Retry-After", "")
        try:
            delays.append(float(header))
        except (ValueError, TypeError):
            try:
                until = parsedate_to_datetime(header)
                delays.append((until - datetime.now(UTC)).total_seconds())
            except (ValueError, TypeError, OverflowError):
                pass
        if isinstance(payload, dict):
            for key in ("retry-after", "retry_after"):
                value = payload.get(key)
                if isinstance(value, (float, int)) and not isinstance(value, bool):
                    delays.append(value)
        self._blocked_until = max(self._blocked_until, time.monotonic() + max(delays))

    @property
    def retry_after_seconds(self):
        return max(0, self._blocked_until - time.monotonic())

    async def _get(self, suffix="", *, missing_vote=False, params=None):
        await self._reserve_request()
        try:
            async with self.http.get(
                API_ROOT + suffix,
                params={"source": "discord"} if missing_vote else params,
                headers={"Authorization": f"Bearer {self._token}", "Accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=4, connect=2),
                allow_redirects=False,
            ) as response:
                if params and "cursor" in params and response.status in {400, 404, 410, 422}:
                    raise TopggCursorExpired("The saved Top.gg vote cursor is no longer valid.")
                if response.status == 404 and missing_vote:
                    return None
                if response.status in {401, 403, 404}:
                    self._blocked_until = time.monotonic() + 60
                    logger.warning("Top.gg read access rejected status=%s", response.status)
                    raise TopggUnavailable(
                        "Vote verification needs an owner configuration check. Your saved rewards are unchanged."
                    )
                if response.status == 429:
                    # Block immediately even if the provider sends invalid JSON.
                    self._backoff(response, None)
                    payload = await self._read_json(response)
                    self._backoff(response, payload)
                    raise TopggUnavailable("Top.gg has paused vote checks. Please try again later.")
                if response.status != 200:
                    logger.warning("Top.gg vote check unavailable status=%s", response.status)
                    raise TopggUnavailable(
                        "Top.gg verification is temporarily unavailable. Please try again later."
                    )
                return await self._read_json(response)
        except (aiohttp.ClientError, TimeoutError):
            logger.warning("Top.gg vote check could not complete")
            raise TopggUnavailable(
                "I couldn't reach top.gg. Please try checking your vote again shortly."
            ) from None

    async def verify_project(self, bot_id: int):
        async with self._identity_lock:
            if self._verified_bot == bot_id:
                return
            data = await self._get()
            if (
                not isinstance(data, dict)
                or data.get("id") != self.project_id
                or data.get("type") != "bot"
                or data.get("platform") != "discord"
                or ("platform_id" in data and data["platform_id"] != str(bot_id))
            ):
                self._blocked_until = time.monotonic() + 60
                raise TopggUnavailable(
                    "The Top.gg token does not match Meyaya's listing. Your saved rewards are unchanged."
                )
            self._verified_bot = bot_id

    async def check_vote(self, bot_id: int, user_id: int) -> VerifiedVote | None:
        await self.verify_project(bot_id)
        cached = self._cache.get(user_id)
        if cached is not None:
            until, vote = cached
            if until > time.monotonic() and (vote is None or vote.expires_at > datetime.now(UTC)):
                self._cache.move_to_end(user_id)
                return vote
            self._cache.pop(user_id)
        data = await self._get(f"/votes/{user_id}", missing_vote=True)
        try:
            vote = parse_vote_status(data, bot_id, user_id) if data is not None else None
        except InvalidVote:
            raise TopggUnavailable(
                "Top.gg returned an invalid vote status. Please try again later."
            ) from None
        self._remember_vote(user_id, vote)
        return vote

    def _remember_vote(self, user_id, vote):
        self._cache[user_id] = (time.monotonic() + (30 if vote else 5), vote)
        self._cache.move_to_end(user_id)
        while len(self._cache) > 512:
            self._cache.popitem(last=False)

    async def vote_page(self, bot_id: int, *, since: datetime, cursor=None) -> VotePage:
        await self.verify_project(bot_id)
        params = {"cursor": cursor} if cursor is not None else {"startDate": since.isoformat()}
        data = await self._get("/votes", params=params)
        try:
            page = parse_vote_page(data, bot_id)
        except InvalidVote:
            raise TopggUnavailable(
                "Top.gg returned an invalid vote page. The scan will be retried."
            ) from None
        for vote in page.votes:
            self._remember_vote(vote.user_id, vote)
        return page
