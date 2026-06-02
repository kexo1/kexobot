from __future__ import annotations

from datetime import datetime
from typing import Any, TypedDict

import asyncpraw.models


class UserRedditData(TypedDict):
    subreddits: tuple[str, ...] | list[str]
    nsfw_posts: bool


class UserData(TypedDict):
    reddit: UserRedditData


class TempUserRedditData(TypedDict):
    viewed_posts: set[str]
    search_limit: int
    last_used: datetime
    multireddit: asyncpraw.models.Multireddit


class TempUserData(TypedDict):
    reddit: TempUserRedditData


class GuildMusicData(TypedDict):
    autoplay_mode: int
    volume: int


class GuildData(TypedDict):
    music: GuildMusicData


class GuildJokesData(TypedDict):
    viewed_jokes: list[str]
    viewed_dad_jokes: list[str]
    viewed_yo_mama_jokes: list[str]


class TempGuildData(TypedDict):
    jokes: GuildJokesData


class NodeCacheEntry(TypedDict):
    password: str
    score: int


TrackExceptionEntry = tuple[Any, Any]
