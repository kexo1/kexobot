"""Dataclass models for persistent and temporary bot data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import asyncpraw.models

from app.config.reddit import SHITPOST_SUBREDDITS_DEFAULT

############################ Persistent Data ############################


@dataclass
class UserRedditData:
    """Reddit-specific settings stored per user."""

    subreddits: list[str] = field(
        default_factory=lambda: list(SHITPOST_SUBREDDITS_DEFAULT)
    )
    nsfw_posts: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "subreddits": list(self.subreddits),
            "nsfw_posts": self.nsfw_posts,
        }


@dataclass
class UserData:
    """Persistent user data stored in MongoDB."""

    reddit: UserRedditData = field(default_factory=UserRedditData)

    def __post_init__(self) -> None:
        if isinstance(self.reddit, dict):
            self.reddit = UserRedditData(**self.reddit)

    def to_dict(self) -> dict[str, Any]:
        return {"reddit": self.reddit.to_dict()}


@dataclass
class GuildMusicData:
    """Music-specific settings stored per guild."""

    autoplay_mode: int = 1
    volume: int = 100

    def to_dict(self) -> dict[str, Any]:
        return {
            "autoplay_mode": self.autoplay_mode,
            "volume": self.volume,
        }


@dataclass
class GuildData:
    """Persistent guild data stored in MongoDB."""

    music: GuildMusicData = field(default_factory=GuildMusicData)

    def __post_init__(self) -> None:
        if isinstance(self.music, dict):
            self.music = GuildMusicData(**self.music)

    def to_dict(self) -> dict[str, Any]:
        return {"music": self.music.to_dict()}


############################ Temporary Data ############################


@dataclass
class GuildJokesData:
    """Temporary joke-tracking per guild."""

    viewed_jokes: list[str] = field(default_factory=list)
    viewed_dad_jokes: list[str] = field(default_factory=list)
    viewed_yo_mama_jokes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "viewed_jokes": self.viewed_jokes,
            "viewed_dad_jokes": self.viewed_dad_jokes,
            "viewed_yo_mama_jokes": self.viewed_yo_mama_jokes,
        }


@dataclass
class TempGuildData:
    """Ephemeral guild state (cleared on restart)."""

    jokes: GuildJokesData = field(default_factory=GuildJokesData)

    def __post_init__(self) -> None:
        if isinstance(self.jokes, dict):
            self.jokes = GuildJokesData(**self.jokes)

    def to_dict(self) -> dict[str, Any]:
        return {"jokes": self.jokes.to_dict()}


@dataclass
class TempUserRedditData:
    """Ephemeral Reddit session data per user."""

    viewed_posts: set[str] = field(default_factory=set)
    search_limit: int = 3
    last_used: datetime | None = None
    multireddit: asyncpraw.models.Multireddit | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "viewed_posts": list(self.viewed_posts),
            "search_limit": self.search_limit,
            "last_used": self.last_used,
            "multireddit": self.multireddit,
        }


@dataclass
class TempUserData:
    """Ephemeral user state (cleared on restart)."""

    reddit: TempUserRedditData = field(default_factory=TempUserRedditData)

    def __post_init__(self) -> None:
        if isinstance(self.reddit, dict):
            # Reconstruct from dict — handle set serialization
            reddit_kw: dict[str, Any] = dict(self.reddit)
            viewed = reddit_kw.pop("viewed_posts", set())
            if isinstance(viewed, list):
                viewed = set(viewed)
            self.reddit = TempUserRedditData(viewed_posts=viewed, **reddit_kw)
