import asyncio
import copy
import logging
import socket
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, cast, override
from zoneinfo import ZoneInfo

import asyncpraw
import asyncprawcore.exceptions
import cloudscraper
import discord
import httpx
import sonolink
from discord import app_commands
from discord.ext import commands, tasks
from pymongo import AsyncMongoClient
from pymongo.asynchronous.collection import AsyncCollection

from app.bot_state import BotState
from app.classes.content_monitor import ContentMonitor
from app.classes.lavalink_server import LavalinkServerManager
from app.classes.reddit_fetcher import RedditFetcher
from app.classes.sfd_servers import SFDServers
from app.config.colors import COLOR_ORANGE_LIGHT, COLOR_RED
from app.config.discord import (
    CHANNEL_ID_FREE_STUFF_CHANNEL,
    CHANNEL_ID_GAME_CRACKS_CHANNEL,
    CHANNEL_ID_GAME_UPDATES_CHANNEL,
    CHANNEL_ID_KEXO_SERVER,
)
from app.config.env import (
    API_WORDNIK,
    ENV_API_DB,
    ENV_DISCORD_TOKEN,
    ENV_HUMOR_KEY,
    LOCAL_MACHINE_NAME,
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
from app.data.bot_data import NodeCacheEntry
from app.response_handler import make_embed, send
from app.utils import get_url_response_time, make_http_request


class KexoBotClient(commands.Bot):
    node: sonolink.Node | None = None
    sonolink_client: sonolink.Client | None = None
    close_nodes_lock: asyncio.Lock | None = None
    user_data_manager: BaseDataManager[UserData] | None = None
    guild_data_manager: BaseDataManager[GuildData] | None = None
    temp_user_data_manager: TempUserDataManager | None = None
    temp_guild_data_manager: TempGuildDataManager | None = None
    joke_cache_manager: JokeCacheManager | None = None
    config_manager: BotConfigManager | None = None
    track_exceptions: (
        dict[int, tuple[sonolink.models.Playable | None, asyncio.Event]] | None
    ) = None
    cached_lavalink_servers: dict[str, NodeCacheEntry] | None = None
    subreddit_icons: dict[str, str] | None = None
    bot_config: AsyncCollection[Any] | None = None
    _bot_config: AsyncCollection[Any] | None = None
    _user_data_db: AsyncCollection[Any] | None = None
    _guild_data_db: AsyncCollection[Any] | None = None
    reddit_agent: asyncpraw.Reddit | None = None
    humor_api_tokens: dict[str, dict[str, bool]] | None = None
    node_is_switching: dict[int, bool] | None = None
    session: httpx.AsyncClient | None = None
    state: BotState | None = None
    connect_node: Callable[..., Awaitable[sonolink.Node | None]] | None = None

    @override
    async def setup_hook(self) -> None:
        """Initialize sonolink client, fetch cached nodes, connect node, load cogs.

        Runs once after login, before any events are processed.
        Only wordnik_presence (needs fully loaded bot) stays in on_ready.
        """
        await kexobot.initialize()
        node = await kexobot.connect_node()
        if not node:
            logging.warning(
                "[Sonolink] Setup hook connect failed, refreshing node cache."
            )
            assert kexobot.lavalink_server_manager is not None, (
                "Lavalink server manager must be initialized"
            )
            await kexobot.lavalink_server_manager.fetch()
            node = await kexobot.connect_node()

        if not node:
            logging.error("[Sonolink] Node is not connected after setup hook attempts.")

        await setup_cogs()
        assert self.sonolink_client is not None, "Sonolink client must be initialized"
        await self.sonolink_client.start()

        main_loop_task.start()
        hourly_loop_task.start()


intents = discord.Intents.default()
intents.message_content = False
intents.members = False

bot = KexoBotClient(command_prefix=commands.when_mentioned, intents=intents)


def load_humor_api_tokens() -> None:
    """Load the humor API tokens."""
    assert bot.humor_api_tokens is not None, "Humor API tokens dict must be initialized"
    bot.humor_api_tokens = {token: {"exhausted": False} for token in ENV_HUMOR_KEY}


def clear_temp_reddit_data() -> None:
    """Clear the temporary user reddit data."""
    assert bot.temp_user_data_manager is not None, (
        "Temp user data manager must be initialized"
    )
    bot.temp_user_data_manager.clear_stale_reddit_data(stale_hours=5)


def clear_temp_guild_data() -> None:
    """Clear the temporary guild data."""
    assert bot.temp_guild_data_manager is not None, (
        "Temp guild data manager must be initialized"
    )
    bot.temp_guild_data_manager.reset_all()


def clear_cached_jokes() -> None:
    """Clear the cached jokes loaded from FunCommands"""
    assert bot.joke_cache_manager is not None, "Joke cache manager must be initialized"
    bot.joke_cache_manager.clear_all()


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

    def __init__(self):
        self.session: httpx.AsyncClient | None = None
        self.cloudscraper_session: cloudscraper.CloudScraper | None = None
        self._user_kexo: discord.User | None = None
        self._subreddit_cache: dict[str, Any] | None = None
        self._hostname: str = socket.gethostname()
        self._main_loop_counter: int = 0

        db = cast(Any, AsyncMongoClient(ENV_API_DB)["KexoBOTDatabase"])  # pyright: ignore[reportAny]
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

        bot.bot_config = self._bot_config
        bot.sonolink_client = sonolink.Client(bot)
        bot.connect_node = self.connect_node
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

        bot.humor_api_tokens = {}
        bot.node_is_switching = {}
        bot.track_exceptions = {}

    async def initialize(self) -> None:
        """Initialize classes and fetch all channels and users."""
        self._create_reddit_agent()
        await self._fetch_users()
        await self._fetch_channels()
        await self._fetch_subreddit_icons()
        await self._fetch_cached_lavalink_servers()
        load_humor_api_tokens()
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
        bot.reddit_agent = self._reddit_agent

    async def _fetch_channels(self) -> None:
        """Fetch all channels for the bot."""
        self._channel_game_updates = await bot.fetch_channel(
            CHANNEL_ID_GAME_UPDATES_CHANNEL
        )
        self._channel_game_cracks = await bot.fetch_channel(
            CHANNEL_ID_GAME_CRACKS_CHANNEL
        )
        self._channel_free_stuff = await bot.fetch_channel(
            CHANNEL_ID_FREE_STUFF_CHANNEL
        )
        logging.info("[Starter] Channels fetched.")

    async def _fetch_cached_lavalink_servers(self) -> None:
        """Fetch cached lavalink servers for the bot."""
        bot.cached_lavalink_servers = await bot.config_manager.get(
            "lavalink_servers", DB_CACHE
        )
        logging.info("[Starter] Cached lavalink servers fetched.")

    async def _fetch_subreddit_icons(self) -> None:
        """Fetch subreddit icons for the bot."""
        bot.subreddit_icons = await bot.config_manager.get("subreddit_icons", DB_CACHE)
        logging.info("[Starter] Subreddit icons fetched.")

    def _define_classes(self) -> None:
        """Define classes for the bot."""
        if self._reddit_agent is None:
            raise RuntimeError("Reddit client is not initialized")

        assert self.cloudscraper_session is not None, (
            "Cloudscraper session must be initialized"
        )
        assert self.session is not None, "HTTP session must be initialized"
        assert bot.config_manager is not None, "Config manager must be initialized"
        assert self._channel_game_updates is not None, (
            "Game updates channel must be fetched"
        )
        assert self._channel_free_stuff is not None, (
            "Free stuff channel must be fetched"
        )
        assert self._channel_game_cracks is not None, (
            "Game cracks channel must be fetched"
        )
        assert self._user_kexo is not None, "User Kexo must be fetched"

        self._content_monitor = ContentMonitor(
            bot.config_manager,
            self.session,
            self.cloudscraper_session,
            self._channel_game_updates,
            self._channel_free_stuff,
            self._user_kexo,
        )

        self._reddit_fetcher = RedditFetcher(
            bot.config_manager,
            self.session,
            self._reddit_agent,
            self._channel_free_stuff,
            self._channel_game_cracks,
        )
        self._sfd_servers = SFDServers(self._bot_config, self.session)
        self._lavalink_server_manager = LavalinkServerManager(bot, self.session)

    async def main_loop(self) -> None:
        """Main loop for the bot.
        This loop runs every minute and runs the different classes that
        fetch data from different sources.
        It runs the classes in a round-robin fashion.
        """
        assert self._reddit_fetcher is not None, "Reddit fetcher must be initialized"
        assert self._content_monitor is not None, "Content monitor must be initialized"
        assert self._sfd_servers is not None, "SFD servers must be initialized"
        now = datetime.now(ZoneInfo("Europe/Bratislava"))

        if self._main_loop_counter == 0:
            self._main_loop_counter = 1
            await self._reddit_fetcher.freegamefindings()

        elif self._main_loop_counter == 1:
            self._main_loop_counter = 2
            await self._content_monitor.alienware_arena()

        elif self._main_loop_counter == 2:
            self._main_loop_counter = 3
            await self._content_monitor.game3rb()

        elif self._main_loop_counter == 3:
            self._main_loop_counter = 4
            await self._content_monitor.online_fix()

        elif self._main_loop_counter == 4:
            self._main_loop_counter = 0
            await self._reddit_fetcher.crackwatch()

        if now.minute % 6 == 0 and self._hostname != LOCAL_MACHINE_NAME:
            await self._sfd_servers.update_stats(now)

    async def hourly_loop(self) -> None:
        """Hourly loop for the bot.
        This loop runs every hour and runs the different classes that
        fetch data from different sources.
        It runs the classes in a round-robin fashion.
        It also updates the reddit cache and fetches lavalink servers.
        """
        assert self._lavalink_server_manager is not None, (
            "Lavalink server manager must be initialized"
        )
        assert bot.cached_lavalink_servers is not None, (
            "Cached lavalink servers must be loaded"
        )
        assert bot.config_manager is not None, "Config manager must be initialized"

        now = datetime.now(ZoneInfo("Europe/Bratislava"))
        weekday = now.weekday()

        if weekday == 6 and now.hour == 0:
            clear_cached_jokes()
            clear_temp_guild_data()
            await self._refresh_subreddit_icons()

        if now.hour % 6 == 0:
            clear_temp_reddit_data()

        if now.hour == 0:
            load_humor_api_tokens()
            await self._upload_cached_lavalink_servers()
            await self._test_all_node_pings()
            await self._lavalink_server_manager.fetch()

        if now.hour == 4:
            assert self.session is not None, "HTTP session must be initialized"
            await self.wordnik_presence()

    async def connect_node(
        self,
        exclude_nodes: list[str] | None = None,
    ) -> sonolink.Node | None:
        """Connect to lavalink node.

        This function will try to connect to the lavalink node
        and if it fails, it will try to connect to the next node.
        If all nodes fail, it will return None.

        Parameters
        ----------
        exclude_nodes: list[str] | None, optional
            A list of lavalink node URIs to exclude from connection attempts.
            This is useful when switching nodes to avoid reconnecting to the same node.

        Returns
        -------
        sonolink.Node | None
            The lavalink node that was connected to.
        """
        node_candidates = copy.deepcopy(bot.cached_lavalink_servers)
        node = None

        for exclude_node in exclude_nodes or []:
            node_candidates.pop(exclude_node, None)

        is_connected = False

        while node_candidates:
            best_score = max(item["score"] for item in node_candidates.values())

            # Filter nodes with the best score
            top_nodes = {
                k: v for k, v in node_candidates.items() if v["score"] == best_score
            }

            if len(top_nodes) > 1:
                # Tiebreaker: pick the node with the lowest ping among top-scoring nodes
                best_ping = min(v["ping"] for v in top_nodes.values())
                top_nodes = {
                    k: v for k, v in top_nodes.items() if v["ping"] == best_ping
                }

            best_node = next(iter(top_nodes.items()))

            node_uri, node_info = best_node
            existing_node = next(
                (n for n in bot.sonolink_client.nodes if n.uri == node_uri),
                None,
            )
            if existing_node and existing_node.is_connected:
                is_connected = await bot.state.node_health_check(existing_node)
                node = existing_node
            else:
                node = bot.state.build_node(node_uri, node_info["password"])
                is_connected = await bot.state.node_attempt_connection(node)

            if is_connected:
                break

            node_candidates.pop(node_uri, None)

        await self._upload_cached_lavalink_servers()

        if not is_connected:
            logging.critical("[Lavalink] No lavalink servers available.")
            return None

        assert node is not None, "Node must be assigned after loop"
        bot.node = node
        return node

    async def wordnik_presence(self) -> None:
        """Fetches the word of the day from Wordnik API."""
        assert self.session is not None, "HTTP session must be initialized"
        json_data = await make_http_request(self.session, API_WORDNIK, get_json=True)
        if not json_data:
            logging.warning("[API] Wordnik API returned no data.")
            return

        assert isinstance(json_data, dict)
        word = cast(str, json_data["word"])
        definition = cast(str, json_data["definitions"][0]["text"])
        definition = definition[:-1]
        presence = f"{word}: {definition}"

        if len(presence) > 128:
            logging.info(f"[API] Presence too long ({word}), skipping.")
            return

        activity = discord.Activity(type=discord.ActivityType.watching, name=presence)
        await bot.change_presence(status=discord.Status.online, activity=activity)
        logging.info(f"[API] Presence set to: {word}")

    async def _refresh_subreddit_icons(self) -> None:
        """Refreshes subreddit icons on Sunday."""
        subreddit_icons: dict[str, str] = {}
        for subreddit_name in SHITPOST_SUBREDDITS_ALL:
            subreddit = await self._reddit_agent.subreddit(subreddit_name)
            assert subreddit is not None, "Subreddit must be resolved"

            try:
                await subreddit.load()
            except asyncprawcore.exceptions.NotFound:
                pass

            icon_img = cast(str, subreddit.icon_img)
            if not icon_img:
                subreddit_icons[subreddit.display_name] = ICON_REDDIT
                continue
            subreddit_icons[subreddit.display_name] = icon_img

        if bot.subreddit_icons == subreddit_icons:
            return

        logging.info("[Reddit] Subreddit icons refreshed.")
        await bot.config_manager.save("subreddit_icons", DB_CACHE)

    async def _fetch_users(self) -> None:
        """Fetch users for the bot."""
        self._user_kexo = await bot.fetch_user(402221830930432000)
        logging.info(f"[Starter] User {self._user_kexo.name} fetched.")

    def _create_http_sessions(self) -> None:
        """Create a httpx session for the bot."""
        self.session = httpx.AsyncClient()
        self.session.headers = httpx.Headers({"User-Agent": USER_AGENT})
        self.cloudscraper_session = cloudscraper.create_scraper()  # pyright: ignore[reportUnknownMemberType]
        logging.info("[Starter] Httpx and cloudscraper session initialized.")

    async def _upload_cached_lavalink_servers(self) -> None:
        """Upload cached lavalink servers to the database."""
        await bot.config_manager.save("lavalink_servers", DB_CACHE)

    async def _test_all_node_pings(self) -> None:
        """Test ping for all cached lavalink nodes and update values.

        Runs daily to refresh ping measurements
        and persist updated values to the database.
        """
        uris = list(bot.cached_lavalink_servers.keys())

        async def ping_one(uri: str) -> None:
            ping = await get_url_response_time(self.session, uri)
            bot.state.change_node_ping(uri, ping)

        await asyncio.gather(*(ping_one(uri) for uri in uris))
        await self._upload_cached_lavalink_servers()
        logging.info("[Lavalink] Daily ping test completed and saved to database.")


kexobot = KexoBot()


def initialize_cog_http_session() -> None:
    """Create a httpx and cloudscraper session for the cogs."""
    bot.session = httpx.AsyncClient()
    bot.session.headers = httpx.Headers({"User-Agent": USER_AGENT})


async def setup_cogs() -> None:
    """Load all cogs for the bot."""

    cogs_list = [
        "fun_commands",
        "commands",
        "music_commands",
        "listeners",
    ]

    initialize_cog_http_session()
    for cog in cogs_list:
        await bot.load_extension(f"app.cogs.{cog}")

    await bot.tree.sync()
    await bot.tree.sync(guild=discord.Object(id=CHANNEL_ID_KEXO_SERVER))

    logging.info("[Starter] Cogs loaded.")


@tasks.loop(minutes=1)
async def main_loop_task() -> None:
    """Main loop for the bot."""
    await kexobot.main_loop()


@tasks.loop(hours=1)
async def hourly_loop_task() -> None:
    """Hourly loop for the bot."""
    await kexobot.hourly_loop()


@main_loop_task.before_loop
async def before_main_loop() -> None:
    """Wait until the bot is ready before starting the main loop."""
    await bot.wait_until_ready()


@hourly_loop_task.before_loop
async def before_hourly_loop() -> None:
    """Wait until the bot is ready before starting the hourly loop."""
    await bot.wait_until_ready()


@bot.event
async def on_ready() -> None:
    """Event that runs when the bot is ready.
    setup_hook handled initialization, node connection, cogs, and loops.
    on_ready only handles presence.
    """
    await kexobot.wordnik_presence()
    logging.info("[Starter] Bot is ready.")


@bot.event
async def on_application_command_error(
    ctx: discord.Interaction, error: discord.app_commands.AppCommandError
) -> None:
    """This event is called when an error occurs in an application command.

    Parameters
    ----------
    ctx: discord.Interaction
        The context of the command that caused the error.
    error: Exception
        The error that occurred.
    """
    if isinstance(error, (commands.CommandOnCooldown, app_commands.CommandOnCooldown)):
        embed = make_embed(
            f"🚫 You're sending too much!, try again in `{round(error.retry_after, 1)}s`.",
            color=COLOR_RED,
            footer="Message will be deleted in 20 seconds.",
        )
        await send(ctx, embed=embed, ephemeral=True, delete_after=20)
        return

    if isinstance(error, commands.MissingPermissions):
        embed = make_embed(
            f"🚫 You don't have the required permissions to use this command.\nRequired permissions: `{', '.join(error.missing_permissions)}`",
            color=COLOR_RED,
        )
        await send(ctx, embed=embed, ephemeral=True)
        return

    if isinstance(error, commands.BotMissingPermissions):
        embed = make_embed(
            f"🚫 I don't have the required permissions to use this command.\nRequired permissions: `{', '.join(error.missing_permissions)}`",
            color=COLOR_RED,
        )
        await send(ctx, embed=embed)
        return

    if isinstance(error, commands.BotMissingRole):
        embed = make_embed(
            f"🚫 You don't have the required role to use this command.\nRequired role: `{error.missing_role}`",
            color=COLOR_RED,
        )
        await send(ctx, embed=embed, ephemeral=True)
        return

    if isinstance(error, discord.errors.NotFound) and "Unknown interaction" in str(
        error
    ):
        embed = make_embed(
            "⚠️ Discord API is not responding. Please try again in a minute.",
            color=COLOR_ORANGE_LIGHT,
        )
        if isinstance(ctx.channel, (discord.TextChannel, discord.Thread)):
            try:
                await ctx.channel.send(embed=embed, delete_after=20)
            except discord.Forbidden:
                pass
        return

    if isinstance(error, commands.NotOwner):
        embed = make_embed(
            "🚫 This command is available only to owner of this bot.",
            color=COLOR_RED,
        )
        await send(ctx, embed=embed, ephemeral=True)
        return

    raise error


@bot.tree.error
async def on_tree_error(
    interaction: discord.Interaction, error: discord.app_commands.AppCommandError
) -> None:
    await on_application_command_error(interaction, error)


@bot.event
async def on_guild_join(guild: discord.Guild) -> None:
    logging.info(f"Joined new guild: {guild.name}")


async def save_all_data() -> None:
    """Save all cached bot config data to MongoDB on shutdown."""
    assert bot.config_manager is not None, "Config manager must be initialized"
    await bot.config_manager.save_all(DB_CACHE)
    logging.info("[MongoDB] All config data saved on shutdown.")


def run_bot() -> None:
    """Run the bot with proper shutdown handling."""
    assert ENV_DISCORD_TOKEN is not None, "DISCORD_TOKEN environment variable not set"
    discord_token: str = ENV_DISCORD_TOKEN
    try:
        bot.run(discord_token)
    finally:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(save_all_data())
        loop.close()


if __name__ == "__main__":
    run_bot()
