import asyncio
import copy
import logging
import socket
from datetime import datetime
from itertools import islice
from zoneinfo import ZoneInfo

import asyncpraw
import asyncpraw.models
import asyncprawcore.exceptions
import cloudscraper
import discord
import httpx
import wavelink
from discord.ext import commands, tasks
from fake_useragent import UserAgent
from pycord.multicog import Bot
from pymongo import AsyncMongoClient
from wavelink.enums import NodeStatus

from app.classes.content_monitor import ContentMonitor
from app.classes.lavalink_server import LavalinkServerManager
from app.classes.reddit_fetcher import RedditFetcher
from app.classes.sfd_servers import SFDServers
from app.constants import (
    API_WORDNIK,
    CHANNEL_ID_ALIENWARE_ARENA_NEWS_CHANNEL,
    CHANNEL_ID_ESUTAZE_CHANNEL,
    CHANNEL_ID_FREE_STUFF_CHANNEL,
    CHANNEL_ID_GAME_UPDATES_CHANNEL,
    DB_CACHE,
    ENV_API_DB,
    ENV_DISCORD_TOKEN,
    ENV_HUMOR_KEY,
    ENV_REDDIT_CLIENT_ID,
    ENV_REDDIT_PASSWORD,
    ENV_REDDIT_SECRET,
    ENV_REDDIT_USER_AGENT,
    ENV_REDDIT_USERNAME,
    ENV_WORDNIK_KEY,
    ICON_REDDIT,
    LOCAL_MACHINE_NAME,
    SHITPOST_SUBREDDITS_ALL,
)
from app.utils import (
    generate_temp_guild_data,
    get_guild_data,
    is_older_than,
    make_http_request,
)

bot = Bot()


async def get_guild_node(guild_id: int) -> tuple[str, dict]:
    """Get the next lavalink node, cycling is guild based.

    Parameters
    ----------
    guild_id: int
        The guild ID to get the node for.

    Returns
    -------
    tuple[str, dict]
        The next lavalink node URI and its metadata.
    """
    _, temp_guild_data = await get_guild_data(bot, guild_id)
    lavalink_server_pos = temp_guild_data["lavalink_server_pos"]

    lavalink_server_pos += 1
    if lavalink_server_pos >= len(bot.cached_lavalink_servers):
        lavalink_server_pos = 0

    temp_guild_data["lavalink_server_pos"] = lavalink_server_pos
    bot.temp_guild_data[guild_id] = temp_guild_data
    return next(
        islice(
            bot.cached_lavalink_servers.items(),
            lavalink_server_pos,
            lavalink_server_pos + 1,
        )
    )


async def check_node_status(node: wavelink.Node) -> bool:
    """Check the status of a lavalink node.
    This function will try to connect to the lavalink node

    Parameters
    ----------
    node: wavelink.Node
        The lavalink node to check the status of.
    Returns
    -------
    bool
        True if the node is connected, False otherwise.
    """
    try:
        await asyncio.wait_for(
            wavelink.Pool.connect(nodes=[node], client=bot), timeout=2
        )
        # Some fucking nodes secretly don't respond,
        # I've played these games before!!!
        await node.fetch_info()
        return True
    except Exception:
        logging.info(f"[Lavalink] Node failed to connect: ({node.uri})")
        bot.cached_lavalink_servers[node.uri]["score"] -= 1
        # Test
        try:
            await node.close(eject=True)
        except Exception:
            await node.close()
    return False


def load_humor_api_tokens() -> None:
    """Load the humor API tokens."""
    bot.humor_api_tokens = {token: {"exhausted": False} for token in ENV_HUMOR_KEY}


async def close_unused_nodes() -> None:
    """Clear unused lavalink nodes.

    This function will check if there are any lavalink nodes
    that are not being used and will close them.
    """
    nodes = list(wavelink.Pool.nodes.values())
    for node in nodes:
        if len(wavelink.Pool.nodes) == 1:
            break

        if len(node.players) == 0:
            logging.info(f"[Lavalink] Node is empty, removing. ({node.uri})")
            await node._pool_closer()  # Node is not properly closed
            try:
                await node.close(eject=True)
            except Exception:
                await node.close()


async def fetch_channel(channel_id: int) -> discord.TextChannel:
    """Helper to fetch a channel by ID, returns :class:`discord.TextChannel`.

    Parameters
    ----------
    channel_id: int
        The ID of the channel to fetch.
    """
    return await bot.fetch_channel(channel_id)


def initialize_class(cls, *args) -> object:
    """Helper to initialize a class with arguments.

    Parameters
    ----------
    cls: type
        The class to initialize.
    *args: tuple
        The arguments to pass to the class.
    """
    return cls(*args)


def get_online_nodes() -> int:
    """Get the number of online lavalink nodes,
    returns ``int`` of online nodes.
    """
    return len(
        [
            node
            for node in wavelink.Pool.nodes.values()
            if node.status == NodeStatus.CONNECTED
        ]
    )


def get_available_nodes() -> int:
    """Get the number of available lavalink nodes.

    Returns the count of cached lavalink nodes.
    """
    return len(bot.cached_lavalink_servers)


def clear_temp_reddit_data() -> None:
    """Clear the temporary user reddit data."""
    if not bot.temp_user_data:
        return

    for _, user_data in bot.temp_user_data.items():
        reddit_data = user_data["reddit"]
        last_used = reddit_data["last_used"]
        if not last_used:
            continue

        if is_older_than(5, last_used):
            reddit_data["last_used"] = None
            reddit_data["viewed_posts"] = set()
            reddit_data["search_limit"] = 3


def clear_temp_guild_data() -> None:
    """Clear the temporary guild data."""
    for guild_id in bot.temp_guild_data:
        bot.temp_guild_data[guild_id] = generate_temp_guild_data()


def clear_cached_jokes() -> None:
    """Clear the cached jokes loaded from FunCommands"""
    bot.loaded_jokes = []
    bot.loaded_dad_jokes = []
    bot.loaded_yo_mama_jokes = []


def build_node(uri: str, password: str) -> wavelink.Node:
    return wavelink.Node(
        uri=uri,
        password=password,
        retries=1,
        inactive_player_timeout=600,
    )


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
        self._subreddit_cache: dict | None = None
        self._hostname = socket.gethostname()
        self._main_loop_counter = 0
        self.cached_lavalink_servers_copy: dict | None = None

        database = AsyncMongoClient(ENV_API_DB)["KexoBOTDatabase"]
        self._bot_config = database["BotConfig"]
        self._user_data_db = database["UserData"]
        self._guild_data_db = database["GuildData"]

        self._reddit_agent = asyncpraw.Reddit(
            client_id=ENV_REDDIT_CLIENT_ID,
            client_secret=ENV_REDDIT_SECRET,
            user_agent=ENV_REDDIT_USER_AGENT,
            username=ENV_REDDIT_USERNAME,
            password=ENV_REDDIT_PASSWORD,
        )

        self._reddit_fetcher: RedditFetcher | None = None
        self._content_monitor: ContentMonitor | None = None
        self._lavalink_server_manager: LavalinkServerManager | None = None
        self._sfd_servers: SFDServers | None = None

        self._channel_esutaze: discord.TextChannel | None = None
        self._channel_game_updates: discord.TextChannel | None = None
        self._channel_free_stuff: discord.TextChannel | None = None
        self._channel_alienware_arena_news: discord.TextChannel | None = None

        # Attach to bot, so we can use it in cogs
        bot.node = None

        bot.user_data = {}
        bot.temp_user_data = {}
        bot.guild_data = {}
        bot.temp_guild_data = {}
        bot.track_exceptions = {}
        bot.cached_lavalink_servers = []

        bot.bot_config = self._bot_config
        bot.user_data_db = self._user_data_db
        bot.guild_data_db = self._guild_data_db

        bot.reddit_agent = self._reddit_agent
        bot.connect_node = self.connect_node
        bot.close_unused_nodes = close_unused_nodes
        bot.get_online_nodes = get_online_nodes
        bot.get_available_nodes = get_available_nodes

        bot.humor_api_tokens = {}
        bot.loaded_jokes = []
        bot.loaded_dad_jokes = []
        bot.loaded_yo_mama_jokes = []

    async def initialize(self) -> None:
        """Initialize the _bot and fetch all channels and users."""
        await self._fetch_users()
        await self._fetch_channels()
        await self._fetch_subreddit_icons()
        await self._fetch_cached_lavalink_servers()
        load_humor_api_tokens()
        self._create_http_sessions()
        self._define_classes()

    async def _fetch_channels(self) -> None:
        """Fetch all channels for the bot."""
        self._channel_esutaze = await fetch_channel(CHANNEL_ID_ESUTAZE_CHANNEL)
        self._channel_game_updates = await fetch_channel(
            CHANNEL_ID_GAME_UPDATES_CHANNEL
        )
        self._channel_free_stuff = await fetch_channel(CHANNEL_ID_FREE_STUFF_CHANNEL)
        self._channel_alienware_arena_news = await fetch_channel(
            CHANNEL_ID_ALIENWARE_ARENA_NEWS_CHANNEL
        )
        logging.info("[Starter] Channels fetched.")

    async def _fetch_cached_lavalink_servers(self) -> None:
        """Fetch cached lavalink servers for the bot."""
        cached_lavalink_servers = await self._bot_config.find_one(DB_CACHE)
        bot.cached_lavalink_servers = cached_lavalink_servers["lavalink_servers"]
        self.cached_lavalink_servers_copy = copy.deepcopy(bot.cached_lavalink_servers)
        logging.info("[Starter] Cached lavalink servers fetched.")

    async def _fetch_subreddit_icons(self) -> None:
        """Fetch subreddit icons for the bot."""
        subreddit_icons = await self._bot_config.find_one(DB_CACHE)
        bot.subreddit_icons = subreddit_icons["subreddit_icons"]
        logging.info("[Starter] Subreddit icons fetched.")

    def _define_classes(self) -> None:
        """Define classes for the bot."""
        self._content_monitor = initialize_class(
            ContentMonitor,
            self._bot_config,
            self.session,
            self.cloudscraper_session,
            self._channel_game_updates,
            self._channel_free_stuff,
            self._channel_esutaze,
            self._channel_alienware_arena_news,
            self._user_kexo,
        )

        self._reddit_fetcher = initialize_class(
            RedditFetcher,
            self._bot_config,
            self.session,
            self._reddit_agent,
            self._channel_free_stuff,
            self._channel_game_updates,
        )
        self._sfd_servers = initialize_class(SFDServers, self._bot_config, self.session)
        self._lavalink_server_manager = initialize_class(
            LavalinkServerManager, bot, self.session
        )

    async def main_loop(self) -> None:
        """Main loop for the bot.
        This loop runs every minute and runs the different classes that
        fetch data from different sources.
        It runs the classes in a round-robin fashion.
        """
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
            self._main_loop_counter = 5
            await self._reddit_fetcher.crackwatch()

        elif self._main_loop_counter == 5:
            self._main_loop_counter = 6
            await self._content_monitor.fanatical()

        elif self._main_loop_counter == 6:
            self._main_loop_counter = 0
            await self._content_monitor.alienware_arena_news()

        if now.minute % 6 == 0 and self._hostname != LOCAL_MACHINE_NAME:
            await self._sfd_servers.update_stats(now)

    async def hourly_loop(self) -> None:
        """Hourly loop for the bot.
        This loop runs every hour and runs the different classes that
        fetch data from different sources.
        It runs the classes in a round-robin fashion.
        It also updates the reddit cache and fetches lavalink servers.
        """
        now = datetime.now(ZoneInfo("Europe/Bratislava"))
        if now.day == 6 and now.hour == 0:
            clear_cached_jokes()
            clear_temp_guild_data()
            await self._refresh_subreddit_icons()

        if now.hour % 6 == 0:
            clear_temp_reddit_data()

        if now.hour == 0:
            load_humor_api_tokens()
            await self._upload_cached_lavalink_servers()
            await self._lavalink_server_manager.fetch()

        if now.hour == 4:
            await self.wordnik_presence()

        await self._content_monitor.power_outages()
        await self._content_monitor.contests()

    async def connect_node(
        self, guild_id: int | None = None, switch_node: bool = True
    ) -> wavelink.Node | None:
        """Connect to lavalink node.

        This function will try to connect to the lavalink node
        and if it fails, it will try to connect to the next node.
        If all nodes fail, it will return None.

        Parameters
        ----------
        guild_id: int
            The guild ID to connect to.
        Returns
        -------
        wavelink.Node | None
            The lavalink node that was connected to.
        """

        # If user requested to reconnect node, we will try to
        # connect to the next node based on the guild ID.
        if guild_id:
            for _ in range(len(bot.cached_lavalink_servers)):
                uri, info = await get_guild_node(guild_id)
                node = build_node(uri, info["password"])
                is_connected = await check_node_status(node)
                if is_connected:
                    return node

        is_connected = False
        node_candidates = copy.deepcopy(bot.cached_lavalink_servers)

        if switch_node:
            try:
                del node_candidates[bot.node.uri]
            except AttributeError:
                logging.critical(
                    f"[Lavalink] Type: {type(bot.node)}, Value: {bot.node}, Repr: {repr(bot.node)}, Full: {bot.node.__dict__}"
                )

        # Try to connect to the best node based on score
        while node_candidates:
            best_node = max(
                node_candidates.items(),
                key=lambda x: x[1]["score"],
            )
            node_uri, node_info = best_node
            node = build_node(node_uri, node_info["password"])
            is_connected = await check_node_status(node)
            if is_connected:
                bot.cached_lavalink_servers[node.uri]["score"] += 1
                break

            del node_candidates[node_uri]

        await self._upload_cached_lavalink_servers()

        if not is_connected:
            logging.critical("[Lavalink] No lavalink servers available.")
            node = None

        bot.node = node
        return node

    async def wordnik_presence(self) -> None:
        """Fetches the word of the day from Wordnik API."""
        url = API_WORDNIK + ENV_WORDNIK_KEY
        json_data = await make_http_request(self.session, url, get_json=True)
        if not json_data:
            logging.warning("[API] Wordnik API returned no data.")
            return

        word = json_data["word"]
        definition = json_data["definitions"][0]["text"]
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
        subreddit_icons = {}
        for subreddit_name in SHITPOST_SUBREDDITS_ALL:
            subreddit: asyncpraw.models.Subreddit = await self._reddit_agent.subreddit(
                subreddit_name
            )
            try:
                await subreddit.load()
            except asyncprawcore.exceptions.NotFound:
                pass

            if not subreddit.icon_img:
                subreddit_icons[subreddit.display_name] = ICON_REDDIT
                continue
            subreddit_icons[subreddit.display_name] = subreddit.icon_img

        if bot.subreddit_icons == subreddit_icons:
            return

        logging.info("[Reddit] Subreddit icons refreshed.")
        await self._bot_config.update_one(
            DB_CACHE, {"$set": {"subreddit_icons": subreddit_icons}}
        )

    async def _fetch_users(self) -> None:
        """Fetch users for the bot."""
        self._user_kexo = await bot.fetch_user(402221830930432000)
        logging.info(f"[Starter] User {self._user_kexo.name} fetched.")

    def _create_http_sessions(self) -> None:
        """Create a httpx session for the bot."""
        self.session = httpx.AsyncClient()
        self.session.headers = httpx.Headers({"User-Agent": UserAgent().random})
        self.cloudscraper_session = cloudscraper.create_scraper()
        logging.info("[Starter] Httpx and cloudscraper session initialized.")

    async def _upload_cached_lavalink_servers(self) -> None:
        """Upload cached lavalink servers to the database."""
        if self.cached_lavalink_servers_copy == bot.cached_lavalink_servers:
            return

        await bot.bot_config.update_one(
            DB_CACHE,
            {"$set": {"lavalink_servers": bot.cached_lavalink_servers}},
        )
        self.cached_lavalink_servers_copy = copy.deepcopy(bot.cached_lavalink_servers)


kexobot = KexoBot()


def initialize_cog_http_session() -> None:
    """Create a httpx and cloudscraper session for the cogs."""
    bot.session = httpx.AsyncClient()
    bot.session.headers = httpx.Headers({"User-Agent": UserAgent().random})


def setup_cogs() -> None:
    """Load all cogs for the bot."""
    cogs_list = [
        "commands",
        "music_commands",
        "listeners",
        "queue_commands",
        "audio_commands",
        "fun_commands",
    ]

    initialize_cog_http_session()
    for cog in cogs_list:
        bot.load_extension(f"app.cogs.{cog}")
    logging.info("[Starter] Cogs loaded.")


setup_cogs()


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


async def bot_loader(main: KexoBot) -> None:
    """This function asynchronously loads the bot and main functions.
    It initializes the bot and starts the main loop and hourly loop.
    It also connects to the lavalink server and sets the presence.

    Parameters
    ----------
    main: KexoBot
        The KexoBot instance to load.
    """

    await main.initialize()
    main_loop_task.start()
    hourly_loop_task.start()

    await main.connect_node(switch_node=False)

    while not main.session:
        await asyncio.sleep(1)
    await main.wordnik_presence()


@bot.event
async def on_ready() -> None:
    """Event that runs when the bot is ready.
    This event is responsible for initializing the bot and
    connecting to the lavalink server.
    It also starts the main loop and the hourly loop.
    """
    logging.info(f"[Starter] Logged in as {bot.user}")
    await bot_loader(kexobot)
    logging.info("[Starter] Bot is ready.")


@bot.event
async def on_application_command_error(ctx: discord.ApplicationContext, error) -> None:
    """This event is called when an error occurs in an application command.

    Parameters
    ----------
    ctx: discord.ApplicationContext
        The context of the command that caused the error.
    error: Exception
        The error that occurred.
    """
    if isinstance(error, commands.CommandOnCooldown):
        embed = discord.Embed(
            title="",
            description=f"🚫 You're sending too much!,"
            f" try again in `{round(error.retry_after, 1)}s`.",
            color=discord.Color.from_rgb(r=220, g=0, b=0),
        )
        embed.set_footer(text="Message will be deleted in 20 seconds.")
        await ctx.respond(embed=embed, ephemeral=True, delete_after=20)
        return

    if isinstance(error, commands.MissingPermissions):
        embed = discord.Embed(
            title="",
            description=f"🚫 You don't have the required permissions to use this command."
            f"\nRequired permissions: `{', '.join(error.missing_permissions)}`",
            color=discord.Color.from_rgb(r=220, g=0, b=0),
        )
        await ctx.respond(embed=embed, ephemeral=True)
        return

    if isinstance(error, commands.BotMissingPermissions):
        embed = discord.Embed(
            title="",
            description=f"🚫 I don't have the required permissions to use this command."
            f"\nRequired permissions: `{', '.join(error.missing_permissions)}`",
            color=discord.Color.from_rgb(r=220, g=0, b=0),
        )
        await ctx.send(embed=embed)
        return

    if isinstance(error, commands.BotMissingRole):
        embed = discord.Embed(
            title="",
            description=f"🚫 You don't have the required role to use this command."
            f"\nRequired role: `{error.missing_role}`",
            color=discord.Color.from_rgb(r=220, g=0, b=0),
        )
        await ctx.respond(embed=embed, ephemeral=True)
        return

    if isinstance(error, discord.errors.NotFound) and "Unknown interaction" in str(
        error
    ):
        embed = discord.Embed(
            title="",
            description="⚠️ Discord API is not responding. Please try again in a minute.",
            color=discord.Color.from_rgb(r=220, g=165, b=0),
        )
        try:
            await ctx.channel.send(embed=embed, delete_after=20)
        except discord.Forbidden:
            pass
        return

    if isinstance(error, discord.ext.commands.NotOwner):
        embed = discord.Embed(
            title="",
            description="🚫 This command is available only to owner of this bot.",
            color=discord.Color.from_rgb(r=220, g=0, b=0),
        )
        await ctx.respond(embed=embed, ephemeral=True)
        return

    raise error


@bot.event
async def on_guild_join(guild: discord.Guild) -> None:
    logging.info(f"Joined new guild: {guild.name}")


bot.run(ENV_DISCORD_TOKEN)
