"""Reusable social interaction framework."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from random import choice

from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.klipy import KlipyService
from bot.services.meyaya_system import MeyayaSystemService
from bot.repositories.relationships import RelationshipRepository
from bot.repositories.users import UserRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class InteractionDefinition:
    """Metadata that defines an interaction command."""

    name: str
    emoji: str
    color: int
    responses: tuple[str, ...]
    gif_urls: tuple[str, ...]
    gif_query: str | None = None
    button_label: str | None = None
    back_command: str | None = None


@dataclass(frozen=True, slots=True)
class InteractionResult:
    """Data returned to the command layer after an interaction is processed."""

    message: str
    gif_url: str | None
    count: int
    title: str


class InteractionService:
    """Business logic for relationship-based interaction commands."""

    def __init__(
        self,
        session: AsyncSession,
        klipy: KlipyService | None = None,
        meyaya_user_id: int | None = None,
    ) -> None:
        self.session = session
        self.relationships = RelationshipRepository(session)
        self.users = UserRepository(session)
        self.klipy = klipy
        self.meyaya_user_id = meyaya_user_id
        self.meyaya_system = MeyayaSystemService(session)

    async def perform(
        self,
        actor_id: int,
        target_id: int,
        definition: InteractionDefinition,
        guild_id: int | None = None,
    ) -> InteractionResult:
        """Update storage and return a response payload for the interaction."""

        if actor_id == target_id:
            message = choice(
                (
                    f"{definition.emoji} You {definition.name} yourself. That is... a choice.",
                    f"{definition.emoji} Self-care {definition.name} moment.",
                )
            )
        else:
            message = choice(definition.responses)
        gif_task = asyncio.create_task(self._find_gif(definition))
        try:
            await self.users.record_interaction(actor_id, target_id, definition.name)
            count = await self.relationships.increment(actor_id, target_id, definition.name)
            if self.meyaya_user_id is not None and target_id == self.meyaya_user_id:
                await self.meyaya_system.apply_interaction(guild_id, actor_id, definition.name)
            await self.session.commit()
        except BaseException:
            gif_task.cancel()
            await asyncio.gather(gif_task, return_exceptions=True)
            raise

        gif_url = await gif_task

        if gif_url is None and definition.gif_urls:
            gif_url = choice(definition.gif_urls)

        return InteractionResult(
            message=message,
            gif_url=gif_url,
            count=count,
            title=f"{definition.emoji} {definition.name.title()}!",
        )

    async def _find_gif(self, definition: InteractionDefinition) -> str | None:
        """Fetch optional media while database writes run in parallel."""

        if self.klipy is None or not definition.gif_query:
            return None
        try:
            return (await self.klipy.random_anime_gif(definition.gif_query)).url
        except Exception:
            logger.warning("Interaction GIF lookup failed name=%s", definition.name, exc_info=True)
            return None
