"""Short transactions finish before avatar downloads, rendering or reveal edits."""

from bot.repositories.fantasy_profiles import FantasyProfileRepository
from bot.services.fantasy_generation import generate_identity


class FantasyProfileService:
    def __init__(self, session):
        self.session = session
        self.profiles = FantasyProfileRepository(session)

    async def get(self, user_id):
        return await self.profiles.get(user_id)

    async def awaken(self, user_id):
        async with self.session.begin():
            existing = await self.profiles.get(user_id)
            if existing is not None:
                return existing, False
            values = generate_identity(user_id)
            return await self.profiles.create_if_absent(values)
