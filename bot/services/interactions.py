"""Reusable social interaction framework."""

from __future__ import annotations

from dataclasses import dataclass
from random import choice

from sqlalchemy.ext.asyncio import AsyncSession

from bot.repositories.relationships import RelationshipRepository
from bot.repositories.users import UserRepository


@dataclass(frozen=True, slots=True)
class InteractionDefinition:
    """Metadata that defines an interaction command."""

    name: str
    emoji: str
    color: int
    responses: tuple[str, ...]
    gif_urls: tuple[str, ...]
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

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.relationships = RelationshipRepository(session)
        self.users = UserRepository(session)

    async def perform(
        self,
        actor_id: int,
        target_id: int,
        definition: InteractionDefinition,
    ) -> InteractionResult:
        """Update storage and return a response payload for the interaction."""

        if actor_id == target_id:
            message = choice((
                f"{definition.emoji} You {definition.name} yourself. That is... a choice.",
                f"{definition.emoji} Self-care {definition.name} moment.",
            ))
        else:
            message = choice(definition.responses)
        await self.users.ensure_user(actor_id)
        await self.users.ensure_user(target_id)
        count = await self.relationships.increment(actor_id, target_id, definition.name)
        await self.session.commit()
        return InteractionResult(
            message=message,
            gif_url=choice(definition.gif_urls) if definition.gif_urls else None,
            count=count,
            title=f"{definition.emoji} {definition.name.title()} complete",
        )
