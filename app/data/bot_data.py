"""Manager for cached bot config data with automatic dirty-checking.

This module provides ``BotConfigManager``, which wraps a MongoDB collection
and an in-memory cache. It automatically tracks whether data has changed
since the last save, and only writes to MongoDB when necessary.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any, TypedDict

from pymongo.asynchronous.collection import AsyncCollection


class NodeCacheEntry(TypedDict):
    """Cached data for a Lavalink node."""

    password: str
    score: int
    ping: int


class BotConfigManager:
    """Manager for cached bot config data with automatic dirty-checking.

    Wraps a MongoDB collection and an in-memory cache. Data is loaded once
    and kept in memory. ``save()`` only writes to MongoDB if the data has
    actually changed since the last save.

    Parameters
    ----------
    collection: :class:`pymongo.AsyncCollection`
        The MongoDB collection to persist data to.
    default_factory: Callable[[], Any]
        Factory function that returns the default empty data structure.
    """

    def __init__(
        self,
        collection: AsyncCollection[Any],
        default_factory: Callable[[], Any],
    ) -> None:
        self._db: AsyncCollection[Any] = collection
        self._default_factory: Callable[[], Any] = default_factory
        self._cache: dict[str, Any] = {}
        self._snapshot: dict[str, Any] = {}

    async def get(self, key: str, query: dict[str, Any]) -> Any:  # pyright: ignore[reportAny]
        """Get cached data by key, loading from MongoDB if needed.

        Parameters
        ----------
        key: str
            Cache key (e.g., ``"lavalink_servers"``).
        query: dict
            MongoDB query to fetch the document if not cached.

        Returns
        -------
        Any
            The cached data for the specified key.
        """
        if key in self._cache:
            return self._cache[key]  # pyright: ignore[reportAny]

        doc = await self._db.find_one(query)
        if doc is not None and key in doc:
            data: Any = doc[key]  # pyright: ignore[reportAny]
        else:
            data = self._default_factory()  # pyright: ignore[reportAny]

        self._cache[key] = data
        self._snapshot[key] = copy.deepcopy(data)  # pyright: ignore[reportAny]
        return data  # pyright: ignore[reportAny]

    def get_cached(self, key: str) -> Any | None:
        """Get data from cache only, without hitting the database.

        Parameters
        ----------
        key: str
            Cache key.

        Returns
        -------
        Any | None
            Cached data if present, else ``None``.
        """
        return self._cache.get(key)

    async def save(self, key: str, query: dict[str, Any]) -> None:
        """Persist data to MongoDB only if it has changed.

        Automatically detects in-place modifications by comparing
        the current cache value to the last saved snapshot.

        Parameters
        ----------
        key: str
            Cache key.
        query: dict
            MongoDB query to match the document.
        """
        current = self._cache.get(key)
        if current is None:
            return

        # Deep copy current state for comparison (handles in-place modifications)
        current_snapshot = copy.deepcopy(current)  # pyright: ignore[reportAny]
        if current_snapshot == self._snapshot.get(key):
            return  # No changes, skip DB write

        await self._db.update_one(
            query,
            {"$set": {key: current}},
            upsert=True,
        )
        self._snapshot[key] = current_snapshot

    async def save_all(self, query: dict[str, Any]) -> None:
        """Save all cached keys that have changed.

        Parameters
        ----------
        query: dict
            MongoDB query to match the document.
        """
        for key in list(self._cache.keys()):
            await self.save(key, query)

    def invalidate(self, key: str) -> None:
        """Remove a key from cache, forcing reload from DB on next ``get()``.

        Parameters
        ----------
        key: str
            Cache key to invalidate.
        """
        self._cache.pop(key, None)
        self._snapshot.pop(key, None)
