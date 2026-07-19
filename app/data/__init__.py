"""Data management layer for persistent and temporary bot state."""

from typing import TYPE_CHECKING

from app.data.base import BaseDataManager
from app.data.bot_data import BotConfigManager
from app.data.models import (
    GuildData,
    GuildJokesData,
    GuildMusicData,
    TempGuildData,
    TempUserData,
    TempUserRedditData,
    UserData,
    UserRedditData,
)
from app.data.temp_guild_data import JokeCacheManager, TempGuildDataManager

if TYPE_CHECKING:
    from app.data.temp_user_data import TempUserDataManager

__all__ = [
    "BaseDataManager",
    "BotConfigManager",
    "GuildData",
    "GuildJokesData",
    "GuildMusicData",
    "JokeCacheManager",
    "TempGuildData",
    "TempGuildDataManager",
    "TempUserData",
    "TempUserDataManager",
    "TempUserRedditData",
    "UserData",
    "UserRedditData",
]
