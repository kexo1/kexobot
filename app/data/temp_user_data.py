"""Manager for ephemeral (non-persisted) user state."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING

import asyncpraw.exceptions
import asyncpraw.models
import asyncprawcore.exceptions

from app.data.models import TempUserData

if TYPE_CHECKING:
    from app.main import KexoBotClient


class TempUserDataManager:
    """Manages temporary (non-persisted) user data.

    Temp data is stored in-memory only and is lost on restart.
    This includes Reddit session state (viewed posts, multireddit, etc.).
    """

    def __init__(self, bot: KexoBotClient | None = None) -> None:
        self._cache: dict[int, TempUserData] = {}
        self._bot = bot

    def get(self, user_id: int) -> TempUserData:
        """Get temporary user data, creating defaults if missing."""
        if user_id not in self._cache:
            self._cache[user_id] = TempUserData()
        return self._cache[user_id]

    async def ensure_multireddit(self, user_id: int) -> None:
        """Generate a multireddit if one doesn't exist yet.

        Preserves existing viewed_posts, search_limit, and last_used.
        """
        temp = self.get(user_id)
        if temp.reddit.multireddit is not None:
            return

        multireddit: asyncpraw.models.Multireddit = (
            await self._bot.reddit_agent.multireddit(
                name=str(user_id), redditor="KexoBOT"
            )
        )
        for attempt in range(3):
            try:
                await multireddit.load()
                break
            except asyncprawcore.exceptions.NotFound:
                logging.warning(
                    "[Reddit] Multireddit for user %s not found. "
                    "Attempting to create it... (Attempt %s/3)",
                    user_id,
                    attempt + 1,
                )
                await asyncio.sleep(attempt + 1)
        else:
            logging.error(
                "[Reddit] Failed to load multireddit for user %s after 3 attempts.",
                user_id,
            )
            return

        # Remove all subreddits first, then add the user's selected ones
        for subreddit in multireddit.subreddits:
            try:
                await multireddit.remove(subreddit)
            except asyncpraw.exceptions.RedditAPIException:
                pass

        user = await self._bot.user_data_manager.get(user_id)

        for subreddit_name in user.reddit.subreddits:
            try:
                await multireddit.add(
                    await self._bot.reddit_agent.subreddit(subreddit_name)
                )
            except asyncpraw.exceptions.RedditAPIException:
                pass

        temp.reddit.multireddit = multireddit

    def clear_stale_reddit_data(self, stale_hours: int = 5) -> None:
        """Reset Reddit session data for users whose session is stale."""
        now = datetime.now()
        for temp in self._cache.values():
            last_used = temp.reddit.last_used
            if last_used is None:
                continue
            diff = now - last_used
            if diff.total_seconds() > stale_hours * 3600:
                temp.reddit.last_used = None
                temp.reddit.viewed_posts = set()
                temp.reddit.search_limit = 3
