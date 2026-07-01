"""Manager for persistent guild data."""

from __future__ import annotations

from app.data.base import BaseDataManager
from app.data.models import GuildData


class GuildDataManager(BaseDataManager[GuildData]):
    """Manager for persistent guild data.

    Extends :class:`BaseDataManager` with guild-specific operations.
    """

    def __init__(self, collection) -> None:
        super().__init__(collection, GuildData)