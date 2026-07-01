"""Generic base manager for persistent data with cache + MongoDB."""

from __future__ import annotations

import logging
from typing import Generic, TypeVar

from pymongo import AsyncMongoClient

T = TypeVar("T")


class BaseDataManager(Generic[T]):
    """Generic manager for a single data type with in-memory cache + MongoDB.

    Provides a consistent ``get`` / ``get_cached`` / ``save`` pattern
    so that cogs never touch raw dicts or the database directly.

    Parameters
    ----------
    collection: :class:`pymongo.AsyncMongoClient`
        The MongoDB collection to persist data to.
    data_class: type[T]
        The dataclass type used for deserialization.
    """

    def __init__(
        self,
        collection: AsyncMongoClient,
        data_class: type[T],  # Can be either UserData or GuildData
    ) -> None:
        self._db = collection
        self._data_class = data_class
        self._cache: dict[int, T] = {}

    async def get(self, _id: int) -> T:
        """Get data by ID, loading from cache or MongoDB.

        If the ID is not cached, it is fetched from MongoDB.
        If it does not exist in the DB, a new instance is created
        and inserted into the DB.

        Parameters
        ----------
        _id: int
            The user or guild ID.

        Returns
        -------
        T
            The deserialized data instance.
        """
        cached = self._cache.get(_id)
        if cached is not None:
            return cached

        raw = await self._db.find_one({"_id": _id})
        if raw is not None:
            raw.pop("_id", None)
            instance: T = self._data_class(**raw)
        else:
            instance = self._data_class()
            logging.info(
                "[MongoDB] Creating new %s for ID: %s",
                self._data_class.__name__,
                _id,
            )
            await self._db.insert_one({"_id": _id, **instance.to_dict()})

        self._cache[_id] = instance
        return instance

    async def save(self, _id: int, data: T) -> None:
        """Persist data to both cache and MongoDB.

        Parameters
        ----------
        _id: int
            The user or guild ID.
        data: T
            The data instance to persist.
        """
        self._cache[_id] = data
        await self._db.update_one(
            {"_id": _id},
            {"$set": data.to_dict()},
            upsert=True,
        )

