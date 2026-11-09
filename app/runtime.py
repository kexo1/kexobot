from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, TypeVar, cast
from zoneinfo import ZoneInfo

import asyncpraw
import asyncprawcore.exceptions
import cloudscraper
import discord
import httpx
import sonolink
from asyncpraw.models.reddit.subreddit.subreddit import Subreddit
from discord.ext import commands
from pymongo import AsyncMongoClient
from pymongo.asynchronous.collection import AsyncCollection

from app.background_tasks import BotBackgroundTasks
from app.bot_state import BotState
from app.classes.content_monitor import ContentMonitor
from app.classes.lavalink_server import LavalinkServerManager
from app.classes.reddit_fetcher import RedditFetcher
from app.classes.sfd_servers import SFDServers
from app.client import KexoBotClient
from app.config.discord import (
    CHANNEL_ID_FREE_STUFF_CHANNEL,
    CHANNEL_ID_GAME_CRACKS_CHANNEL,
    CHANNEL_ID_GAME_UPDATES_CHANNEL,
)
from app.config.env import (
    API_WORDNIK,
    ENV_API_DB,
    ENV_DISCORD_TOKEN,
    ENV_HUMOR_KEY,
    USER_AGENT,
)
from app.config.mongo import DB_CACHE
from app.config.reddit import (
    ENV_REDDIT_CLIENT_ID,
    ENV_REDDIT_PASSWORD,
    ENV_REDDIT_SECRET,
    ENV_REDDIT_USER_AGENT,
    ENV_REDDIT_USERNAME,
    ICON_REDDIT,
    SHITPOST_SUBREDDITS_ALL,
)
from app.data import (
    BaseDataManager,
    BotConfigManager,
    GuildData,
    JokeCacheManager,
    TempGuildDataManager,
    TempUserDataManager,
    UserData,
)
from app.events import register_events
from app.extension_loader import setup_extensions
from app.services.lavalink import LavalinkNodeService
from app.utils import make_http_request

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _require_initialized(value: T | None, resource: str) -> T:
    if value is None:
        raise RuntimeError(f"{resource} has not been initialized")
    return value


intents = discord.Intents.default()
intents.message_content = False
intents.members = False


class KexoBot:
    """Main class for the _bot.
    This class is responsible for initializing the _bot, creating the session,
    and connecting to the lavalink server.
    It also contains the main loop and the hourly loop.
    The main loop is responsible for running the different classes that
    fetch data from different sources.
    The hourly loop is responsible for updating the reddit cache and
    fetching lavalink servers.
    """

    def __init__(self, bot: KexoBotClient):
        self.bot = bot
        self.background_tasks = BotBackgroundTasks(bot, self)
        self.session: httpx.AsyncClient | None = None
        self.cloudscraper_session: cloudscraper.CloudScraper | None = None
        self._user_kexo: discord.User | None = None
        self._subreddit_cache: dict[str, Any] | None = None
        self._hostname: str = socket.gethostname()
        self._main_loop_counter: int = 0
        self._is_shutdown = False

        self._mongo_client: AsyncMongoClient[Any] = AsyncMongoClient(ENV_API_DB)
        db = cast(Any, self._mongo_client["KexoBOTDatabase"])  # pyright: ignore[reportAny]
        self._bot_config: AsyncCollection[Any] = cast(
            AsyncCollection[Any], db["BotConfig"]
        )
        self._user_data_db: AsyncCollection[Any] = cast(
            AsyncCollection[Any], db["UserData"]
        )
        self._guild_data_db: AsyncCollection[Any] = cast(
            AsyncCollection[Any], db["GuildData"]
        )

        self._reddit_agent: asyncpraw.Reddit | None = None

        self._reddit_fetcher: RedditFetcher | None = None
        self._content_monitor: ContentMonitor | None = None
        self._lavalink_server_manager: LavalinkServerManager | None = None
        self._sfd_servers: SFDServers | None = None

        self.lavalink_server_manager: LavalinkServerManager | None = None

        self._channel_game_updates: discord.TextChannel | None = None
        self._channel_game_cracks: discord.TextChannel | None = None
        self._channel_free_stuff: discord.TextChannel | None = None

        # Attach to bot, so we can use it in cogs
        bot.node = None
        bot.cached_lavalink_servers = {}
        bot.close_nodes_lock = asyncio.Lock()
        bot.connect_node_lock = asyncio.Lock()

        bot.bot_config = self._bot_config
        bot.sonolink_client = sonolink.Client(bot)
        bot.state = BotState(bot)

        # Data managers (replace old raw dicts)
        bot.user_data_manager = BaseDataManager[UserData](self._user_data_db, UserData)
        bot.guild_data_manager = BaseDataManager[GuildData](
            self._guild_data_db, GuildData
        )
        bot.temp_user_data_manager = TempUserDataManager(bot)
        bot.temp_guild_data_manager = TempGuildDataManager()
        bot.joke_cache_manager = JokeCacheManager()
        bot.config_manager = BotConfigManager(self._bot_config, lambda: list[str]())
        self._lavalink_node_service = LavalinkNodeService(bot)
        bot.connect_node = self._lavalink_node_service.connect_node

        bot.humor_api_tokens = {}
        bot.node_is_switching = {}
        bot.reconnecting = False
        bot.track_exceptions = {}

    async def setup(self) -> None:
        """Initialize runtime services and Discord extensions."""
        await self.initialize()
        node = await self._lavalink_node_service.connect_node()
        if not node:
            logger.warning(
                "[Sonolink] Setup hook connect failed, refreshing node cache."
            )
            server_manager = _require_initialized(
                self._lavalink_server_manager,
                "Lavalink server manager",
            )
            await server_manager.fetch()
            node = await self._lavalink_node_service.connect_node()

        if not node:
            logger.error("[Sonolink] Node is not connected after setup hook attempts.")

        await setup_extensions(self.bot)
        await self.bot.sonolink_client.start()
        self.background_tasks.start()

    async def initialize(self) -> None:
        """Initialize classes and fetch all channels and users."""
        self._create_reddit_agent()
        await self._fetch_users()
        await self._fetch_channels()
        await self._fetch_subreddit_icons()
        await self._fetch_cached_lavalink_servers()
        self._load_humor_api_tokens()
        self._create_http_sessions()
        self._define_classes()

    def _create_reddit_agent(self) -> None:
        """Create Reddit API client in runtime initialization context."""
        self._reddit_agent = asyncpraw.Reddit(
            client_id=ENV_REDDIT_CLIENT_ID,
            client_secret=ENV_REDDIT_SECRET,
            user_agent=ENV_REDDIT_USER_AGENT,
            username=ENV_REDDIT_USERNAME,
            password=ENV_REDDIT_PASSWORD,
        )
        self.bot.reddit_agent = self._reddit_agent

    async def _fetch_channels(self) -> None:
        """Fetch all channels for the bot."""
        self._channel_game_updates = cast(
            discord.TextChannel,
            await self.bot.fetch_channel(CHANNEL_ID_GAME_UPDATES_CHANNEL),
        )
        self._channel_game_cracks = cast(
            discord.TextChannel,
            await self.bot.fetch_channel(CHANNEL_ID_GAME_CRACKS_CHANNEL),
        )
        self._channel_free_stuff = cast(
            discord.TextChannel,
            await self.bot.fetch_channel(CHANNEL_ID_FREE_STUFF_CHANNEL),
        )
        logger.info("[Starter] Channels fetched.")

    async def _fetch_cached_lavalink_servers(self) -> None:
        """Fetch cached lavalink servers for the bot."""
        self.bot.cached_lavalink_servers = await self.bot.config_manager.get(
            "lavalink_servers", DB_CACHE
        )
        logger.info("[Starter] Cached lavalink servers fetched.")

    async def _fetch_subreddit_icons(self) -> None:
        """Fetch subreddit icons for the bot."""
        self.bot.subreddit_icons = await self.bot.config_manager.get(
            "subreddit_icons", DB_CACHE
        )
        logger.info("[Starter] Subreddit icons fetched.")

    def _define_classes(self) -> None:
        """Define classes for the bot."""
        reddit_agent = _require_initialized(self._reddit_agent, "Reddit client")
        cloudscraper_session = _require_initialized(
            self.cloudscraper_session,
            "Cloudscraper session",
        )
        session = _require_initialized(self.session, "HTTP session")
        game_updates_channel = _require_initialized(
            self._channel_game_updates,
            "Game updates channel",
        )
        free_stuff_channel = _require_initialized(
            self._channel_free_stuff,
            "Free stuff channel",
        )
        game_cracks_channel = _require_initialized(
            self._channel_game_cracks,
            "Game cracks channel",
        )
        user_kexo = _require_initialized(self._user_kexo, "Kexo user")

        self._content_monitor = ContentMonitor(
            self.bot.config_manager,
            session,
            cloudscraper_session,
            game_updates_channel,
            free_stuff_channel,
            user_kexo,
        )

        self._reddit_fetcher = RedditFetcher(
            self.bot.config_manager,
            session,
            reddit_agent,
            free_stuff_channel,
            game_cracks_channel,
        )
        self._sfd_servers = SFDServers(self._bot_config, session)
        self._lavalink_server_manager = LavalinkServerManager(self.bot, session)

    async def main_loop(self) -> None:
        """Main loop for the bot.
        This loop runs every minute and runs the different classes that
        fetch data from different sources.
        It runs the classes in a round-robin fashion.
        """
        reddit_fetcher = _require_initialized(self._reddit_fetcher, "Reddit fetcher")
        content_monitor = _require_initialized(
            self._content_monitor,
            "Content monitor",
        )
        _require_initialized(self._sfd_servers, "SFD servers")
        # now = datetime.now(ZoneInfo("Europe/Bratislava"))

        if self._main_loop_counter == 0:
            self._main_loop_counter = 1
            await reddit_fetcher.freegamefindings()

        elif self._main_loop_counter == 1:
            self._main_loop_counter = 2
            # await self._content_monitor.alienware_arena()

        elif self._main_loop_counter == 2:
            self._main_loop_counter = 3
            await content_monitor.game3rb()

        elif self._main_loop_counter == 3:
            self._main_loop_counter = 4
            await content_monitor.online_fix()

        elif self._main_loop_counter == 4:
            self._main_loop_counter = 0
            await reddit_fetcher.crackwatch()

        # if now.minute % 6 == 0 and self._hostname != LOCAL_MACHINE_NAME:
        #    await self._sfd_servers.update_stats(now)

    async def hourly_loop(self) -> None:
        """Hourly loop for the bot.
        This loop runs every hour and runs the different classes that
        fetch data from different sources.
        It runs the classes in a round-robin fashion.
        It also updates the reddit cache and fetches lavalink servers.
        """
        server_manager = _require_initialized(
            self._lavalink_server_manager,
            "Lavalink server manager",
        )

        now = datetime.now(ZoneInfo("Europe/Bratislava"))
        weekday = now.weekday()

        if weekday == 6 and now.hour == 0:
            self.bot.joke_cache_manager.clear_all()
            self.bot.temp_guild_data_manager.reset_all()
            await self._refresh_subreddit_icons()

        if now.hour % 6 == 0:
            self.bot.temp_user_data_manager.clear_stale_reddit_data(stale_hours=5)

        if now.hour == 0:
            self._load_humor_api_tokens()
            await self._lavalink_node_service.upload_cached_servers()
            await self._lavalink_node_service.test_all_node_pings(
                _require_initialized(self.session, "HTTP session")
            )
            await server_manager.fetch()

        if now.hour == 4:
            await self.wordnik_presence()

    async def wordnik_presence(self) -> None:
        """Fetches the word of the day from Wordnik API."""
        session = _require_initialized(self.session, "HTTP session")
        json_data = await make_http_request(session, API_WORDNIK, get_json=True)
        if not json_data:
            logger.warning("[API] Wordnik API returned no data.")
            return

        if not isinstance(json_data, dict):
            logger.warning("[API] Wordnik API returned data in an unexpected format.")
            return
        response = cast(dict[str, object], json_data)
        word = response.get("word")
        definitions = response.get("definitions")
        if not isinstance(word, str) or not isinstance(definitions, list):
            logger.warning("[API] Wordnik API response is missing word definitions.")
            return
        definition_items = cast(list[object], definitions)
        if not definition_items or not isinstance(definition_items[0], dict):
            logger.warning("[API] Wordnik API response is missing word definitions.")
            return
        definition_data = cast(dict[str, object], definition_items[0])
        definition = definition_data.get("text")
        if not isinstance(definition, str):
            logger.warning("[API] Wordnik API response is missing word definitions.")
            return
        definition = definition[:-1]
        presence = f"{word}: {definition}"

        if len(presence) > 128:
            logger.info(f"[API] Presence too long ({word}), skipping.")
            return

        activity = discord.Activity(type=discord.ActivityType.watching, name=presence)
        await self.bot.change_presence(status=discord.Status.online, activity=activity)
        logger.info(f"[API] Presence set to: {word}")

    async def _refresh_subreddit_icons(self) -> None:
        """Refreshes subreddit icons on Sunday."""
        subreddit_icons: dict[str, str] = {}
        for subreddit_name in SHITPOST_SUBREDDITS_ALL:
            subreddit: Subreddit = await self.bot.reddit_agent.subreddit(subreddit_name)

            try:
                await subreddit.load()
            except asyncprawcore.exceptions.NotFound:
                continue

            icon_img = cast(str, subreddit.icon_img)
            if not icon_img:
                subreddit_icons[subreddit.display_name] = ICON_REDDIT
                continue
            subreddit_icons[subreddit.display_name] = icon_img

        if self.bot.subreddit_icons == subreddit_icons:
            return

        logger.info("[Reddit] Subreddit icons refreshed.")
        await self.bot.config_manager.save("subreddit_icons", DB_CACHE)

    async def _fetch_users(self) -> None:
        """Fetch users for the bot."""
        self._user_kexo = await self.bot.fetch_user(402221830930432000)
        logger.info(f"[Starter] User {self._user_kexo.name} fetched.")

    def _create_http_sessions(self) -> None:
        """Create a httpx session for the bot."""
        self.session = httpx.AsyncClient()
        self.session.headers = httpx.Headers({"User-Agent": USER_AGENT})
        self.cloudscraper_session = cloudscraper.create_scraper()  # pyright: ignore[reportUnknownMemberType]
        logger.info("[Starter] Httpx and cloudscraper session initialized.")

    def _load_humor_api_tokens(self) -> None:
        self.bot.humor_api_tokens = {
            token: {"exhausted": False} for token in ENV_HUMOR_KEY
        }

    async def save_all_data(self) -> None:
        """Save all cached bot config data to MongoDB on shutdown."""
        await self.bot.config_manager.save_all(DB_CACHE)
        logger.info("[MongoDB] All config data saved on shutdown.")

    async def shutdown(self) -> None:
        """Stop background work, persist state, and release owned resources."""
        if self._is_shutdown:
            return
        self._is_shutdown = True

        errors: list[Exception] = []

        async def run_step(name: str, operation: Callable[[], Awaitable[None]]) -> None:
            try:
                await operation()
            except Exception as exc:
                logger.exception("[Shutdown] Failed to %s.", name)
                errors.append(exc)

        await run_step("stop background tasks", self.background_tasks.stop)
        await run_step("save cached data", self.save_all_data)
        await run_step("close Lavalink client", self.bot.sonolink_client.close)
        if self._reddit_agent is not None:
            await run_step("close Reddit client", self._reddit_agent.close)
        if self.session is not None:
            await run_step("close HTTP session", self.session.aclose)
        if self.cloudscraper_session is not None:
            try:
                self.cloudscraper_session.close()
            except Exception as exc:
                logger.exception("[Shutdown] Failed to close cloudscraper session.")
                errors.append(exc)
        await run_step("close MongoDB client", self._mongo_client.close)

        if errors:
            raise ExceptionGroup("Bot runtime shutdown encountered errors", errors)


def create_bot() -> KexoBotClient:
    """Create the Discord client and its runtime dependencies."""
    bot = KexoBotClient(command_prefix=commands.when_mentioned, intents=intents)
    runtime = KexoBot(bot)
    bot.runtime = runtime
    register_events(bot, runtime)
    return bot


def run_bot() -> None:
    """Run the bot with proper shutdown handling."""
    if ENV_DISCORD_TOKEN is None:
        raise RuntimeError("DISCORD_TOKEN environment variable not set")
    discord_token: str = ENV_DISCORD_TOKEN
    bot = create_bot()
    bot.run(discord_token)
