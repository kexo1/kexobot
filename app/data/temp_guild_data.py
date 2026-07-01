"""Manager for ephemeral (non-persisted) guild state."""

from __future__ import annotations

from app.data.models import TempGuildData


class JokeCacheManager:
    """Manages global joke caches (shared across all guilds)."""

    def __init__(self) -> None:
        self.loaded_jokes: set[str] = set()
        self.loaded_dad_jokes: set[str] = set()
        self.loaded_yo_mama_jokes: set[str] = set()

    def clear_all(self) -> None:
        """Clear all in-memory joke caches."""
        self.loaded_jokes.clear()
        self.loaded_dad_jokes.clear()
        self.loaded_yo_mama_jokes.clear()


class TempGuildDataManager:
    """Manages temporary (non-persisted) guild data.

    Temp data is stored in-memory only and is lost on restart.
    This includes joke tracking per guild.
    """

    def __init__(self) -> None:
        self._cache: dict[int, TempGuildData] = {}

    def get(self, guild_id: int) -> TempGuildData:
        """Get temporary guild data, creating defaults if missing."""
        if guild_id not in self._cache:
            self._cache[guild_id] = TempGuildData()
        return self._cache[guild_id]

    def reset_all(self) -> None:
        """Reset temporary data for all guilds to defaults."""
        for guild_id in self._cache:
            self._cache[guild_id] = TempGuildData()