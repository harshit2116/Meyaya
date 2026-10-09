"""Short transactions finish before avatar downloads, rendering or reveal edits."""

from bot.repositories.fantasy_profiles import FantasyProfileRepository
from bot.services.fantasy_generation import generate_identity
from datetime import UTC, datetime, timedelta
from bot.data.fantasy_alignment import PATRONS, patron_for, alignment_values
from bot.repositories.fantasy_dungeon import FantasyDungeonRepository
from bot.services.fantasy_progression import growth_values

REBIRTH_COOLDOWN = timedelta(hours=24)


def utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class RebirthUnavailable(ValueError):
    pass


class AlignmentUnavailable(ValueError):
    pass


class FantasyProfileService:
    def __init__(self, session):
        self.session = session
        self.profiles = FantasyProfileRepository(session)

    async def get(self, user_id):
        return await self.profiles.get(user_id)

    async def reset(self, user_id):
        """Explicit owner administration only; ordinary awakening never calls this."""
        async with self.session.begin():
            return await self.profiles.reset(user_id)

    async def choose_alignment(self, user_id, expected_awakening, choice):
        if choice not in PATRONS:
            raise AlignmentUnavailable("That presence cannot claim a soul.")
        async with self.session.begin():
            profile = await self.profiles.locked(user_id)
            if profile is None or utc(profile.awakened_at) != utc(expected_awakening):
                raise AlignmentUnavailable("Your identity changed. Open `/fantasyprofile` again.")
            if patron_for(profile):
                raise AlignmentUnavailable(
                    "Your oath is already sealed. Only rebirth can change it."
                )
            if await FantasyDungeonRepository(self.session).active(user_id):
                raise AlignmentUnavailable("Abandon or finish your dungeon before changing allegiance.")
            return await self.profiles.replace_identity(user_id, alignment_values(profile, choice))

    async def rebirth(self, user_id, expected_awakening, *, now=None):
        """Lock, revalidate, reroll and commit together; no rendering in this transaction."""
        async with self.session.begin():
            profile = await self.profiles.locked(user_id)
            if profile is None or utc(profile.awakened_at) != utc(expected_awakening):
                raise RebirthUnavailable(
                    "Your identity changed. Open `/rebirth` again before confirming."
                )
            if await FantasyDungeonRepository(self.session).active(user_id):
                raise RebirthUnavailable("Abandon or finish your dungeon before rebirth.")
            current = utc(now) if now else datetime.now(UTC)
            last = profile.last_rebirth_at
            if last and current < utc(last) + REBIRTH_COOLDOWN:
                ready = int((utc(last) + REBIRTH_COOLDOWN).timestamp())
                raise RebirthUnavailable(
                    f"Your next rebirth is available <t:{ready}:R> (24-hour cooldown)."
                )
            values = generate_identity(user_id, now=current)
            values.update(level=profile.level, xp=profile.xp,
                          weapon_level=profile.weapon_level, highest_floor=profile.highest_floor,
                          ending_route=profile.ending_route, ending_chosen_at=profile.ending_chosen_at,
                          ending_completed_at=profile.ending_completed_at)
            values.update(growth_values(values, profile.level))
            values.update(hp=values["max_hp"], mp=values["max_mp"])
            values.update(rebirth_count=(profile.rebirth_count or 0) + 1, last_rebirth_at=current)
            return await self.profiles.replace_identity(user_id, values)

    async def awaken(self, user_id):
        async with self.session.begin():
            existing = await self.profiles.get(user_id)
            if existing is not None:
                return existing, False
            values = generate_identity(user_id)
            return await self.profiles.create_if_absent(values)
