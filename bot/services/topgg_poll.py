"""Bounded vote-history scans, checkpointed alongside newly awarded receipts."""

import asyncio
from uuid import uuid4

from bot.services.topgg_api import TopggCursorExpired, TopggUnavailable


class TopggPoller:
    def __init__(self, api, votes, bot_id, project_id):
        self.api = api
        self.votes = votes
        self.bot_id = bot_id
        self.project_id = project_id

    async def poll_once(self):
        owner = uuid4().hex
        acquired = False
        try:
            async with asyncio.timeout(25):
                checkpoint = await self.votes.acquire_poll(self.project_id, owner)
                if checkpoint is None:
                    return 0
                acquired = True
                cursor = checkpoint.cursor
                seen = {cursor}
                inserted = 0
                # Keep room in the shared API budget for interactive checks.
                # Large scans continue from the persisted cursor on the next tick.
                for _ in range(3):
                    try:
                        page = await self.api.vote_page(
                            self.bot_id, since=checkpoint.since, cursor=cursor
                        )
                    except TopggCursorExpired:
                        await self.votes.reset_poll_cursor(self.project_id, owner)
                        return inserted
                    if not page.complete and page.cursor in seen:
                        raise TopggUnavailable("Top.gg vote pagination did not advance.")
                    inserted += await self.votes.store_poll_page(self.project_id, owner, page)
                    if page.complete:
                        return inserted
                    cursor = page.cursor
                    seen.add(cursor)
                return inserted
        finally:
            if acquired:
                async with asyncio.timeout(5):
                    await self.votes.release_poll(self.project_id, owner)
