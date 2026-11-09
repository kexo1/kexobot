from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import asyncpraw
import httpx
import sonolink
from discord.ext import commands
from pymongo.asynchronous.collection import AsyncCollection
from typing_extensions import override

from app.bot_state import BotState
from app.data import (
    BaseDataManager,
    BotConfigManager,
    GuildData,
    JokeCacheManager,
    TempGuildDataManager,
    TempUserDataManager,
    UserData,
)
from app.data.bot_data import NodeCacheEntry
from app.runtime_protocol import BotRuntime


class KexoBotClient(commands.Bot):
    node: sonolink.Node | None = None
    sonolink_client: sonolink.Client
    close_nodes_lock: asyncio.Lock
    connect_node_lock: asyncio.Lock
    user_data_manager: BaseDataManager[UserData]
    guild_data_manager: BaseDataManager[GuildData]
    temp_user_data_manager: TempUserDataManager
    temp_guild_data_manager: TempGuildDataManager
    joke_cache_manager: JokeCacheManager
    config_manager: BotConfigManager
    track_exceptions: dict[int, tuple[sonolink.models.Playable | None, asyncio.Event]]
    cached_lavalink_servers: dict[str, NodeCacheEntry]
    subreddit_icons: dict[str, str]
    bot_config: AsyncCollection[Any]
    reddit_agent: asyncpraw.Reddit
    humor_api_tokens: dict[str, dict[str, bool]]
    node_is_switching: dict[int, bool]
    reconnecting: bool = False
    session: httpx.AsyncClient
    state: BotState
    connect_node: Callable[..., Awaitable[sonolink.Node | None]]
    runtime: BotRuntime

    @override
    async def setup_hook(self) -> None:
        """Initialize application services before the bot starts receiving events."""
        await self.runtime.setup()

    @override
    async def close(self) -> None:
        """Shut down application resources before closing the Discord client."""
        try:
            await self.runtime.shutdown()
        finally:
            await super().close()
