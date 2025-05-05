import asyncio
import socket
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import aiohttp
import asyncpraw
import asyncpraw.models
import asyncprawcore.exceptions
import discord
import dns.resolver
import httpx
import wavelink
from discord.ext import tasks, commands
from fake_useragent import UserAgent
from motor.motor_asyncio import AsyncIOMotorClient
from pycord.multicog import Bot
from wavelink.enums import NodeStatus

from app.classes.content_monitor import ContentMonitor
from app.classes.lavalink_server import LavalinkServerManager
from app.classes.reddit_fetcher import RedditFetcher
from app.classes.sfd_servers import SFDServers
from app.constants import (
    DISCORD_TOKEN,
    MONGO_DB_URL,
    REDDIT_PASSWORD,
    REDDIT_SECRET,
    REDDIT_USER_AGENT,
    REDDIT_USERNAME,
    REDDIT_CLIENT_ID,
    SHITPOST_SUBREDDITS_ALL,
    DB_CACHE,
    ESUTAZE_CHANNEL,
    GAME_UPDATES_CHANNEL,
    FREE_STUFF_CHANNEL,
    ALIENWARE_ARENA_NEWS_CHANNEL,
    HUMOR_API_SECRET,
    KEXO_SERVER,
    LOCAL_MACHINE_NAME,
)
from app.utils import get_guild_data, is_older_than, generate_temp_guild_data

dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ["8.8.8.8"]

bot = Bot()


class KexoBot:
    """Main class for the _bot.
    This class is responsible for initializing the _bot, creating the _session,
    and connecting to the lavalink server.
    It also contains the main loop and the hourly loop.
    The main loop is responsible for running the different classes that
    fetch data from different sources.
    The hourly loop is responsible for updating the reddit cache and
    fetching lavalink servers.
    """

    def __init__(self):
        self._user_kexo = None | discord.User
        self._session = None | httpx.AsyncClient
        self._subreddit_cache = None | dict
        self._hostname = socket.gethostname()
        self._main_loop_counter = 0
        self.lavalink_servers: list[wavelink.Node] = []
        self._offline_lavalink_servers: list[str] = []

        database = AsyncIOMotorClient(MONGO_DB_URL)["KexoBOTDatabase"]
        self._bot_config = database["BotConfig"]
        self._user_data_db = database["UserData"]
        self._guild_data_db = database["GuildData"]

        self._reddit_agent = asyncpraw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_SECRET,
            user_agent=REDDIT_USER_AGENT,
            username=REDDIT_USERNAME,
            password=REDDIT_PASSWORD,
        )

        # Attach _bot, so we can use it in cogs
        # Database
        bot.user_data = {}
        bot.temp_user_data = {}
        bot.guild_data = {}
        bot.temp_guild_data = {}
        bot.bot_config = self._bot_config
        bot.user_data_db = self._user_data_db
        bot.guild_data_db = self._guild_data_db
        # Functions
        bot.reddit_agent = self._reddit_agent
        bot.connect_node = self.connect_node
        bot.close_unused_nodes = self.close_unused_nodes
        bot.get_online_nodes = self.get_online_nodes
        bot.get_avaiable_nodes = self.get_avaiable_nodes
        # Other
        bot.humor_api_tokens = {}
        bot.loaded_jokes = []
        bot.loaded_dad_jokes = []
        bot.loaded_yo_mama_jokes = []

        # Initialize class variables
        self._reddit_fetcher = None | RedditFetcher
        self._content_monitor = None | ContentMonitor
        self._lavalink_server_manager = None | LavalinkServerManager
        self._sfd_servers = None | SFDServers
        self._esutaze_channel = None | discord.TextChannel
        self._game_updates_channel = None | discord.TextChannel
        self._free_stuff_channel = None | discord.TextChannel
        self._alienware_arena_news_channel = None | discord.TextChannel

    async def initialize(self) -> None:
        """Initialize the _bot and fetch all channels and users."""
        await self._fetch_users()
        await self._fetch_channels()
        await self._fetch_subreddit_icons()
        self._load_humor_api_tokens()
        self._create_session()
        self._define_classes()
        bot.sfd_servers = self._sfd_servers

    @staticmethod
    async def _fetch_channel(channel_id: int) -> discord.TextChannel:
        """Helper to fetch a channel by ID."""

        return await bot.fetch_channel(channel_id)

    @staticmethod
    def _initialize_class(cls, *args):
        """Helper to initialize a class with arguments."""
        return cls(*args)

    async def _fetch_channels(self) -> None:
        """Fetch all channels for the bot."""
        self._esutaze_channel = await self._fetch_channel(ESUTAZE_CHANNEL)
        self._game_updates_channel = await self._fetch_channel(GAME_UPDATES_CHANNEL)
        self._free_stuff_channel = await self._fetch_channel(FREE_STUFF_CHANNEL)
        self._alienware_arena_news_channel = await self._fetch_channel(
            ALIENWARE_ARENA_NEWS_CHANNEL
        )
        print("Channels fetched.")

    async def _fetch_subreddit_icons(self) -> None:
        """Fetch subreddit icons for the bot."""
        subreddit_icons = await self._bot_config.find_one(DB_CACHE)
        bot.subreddit_icons = subreddit_icons["subreddit_icons"]
        print("Subreddit icons fetched.")

    @staticmethod
    def _load_humor_api_tokens() -> None:
        """Load the humor API tokens."""
        bot.humor_api_tokens = {}
        for token in HUMOR_API_SECRET:
            bot.humor_api_tokens[token] = {
                "exhausted": False,
            }

    def _define_classes(self) -> None:
        """Define classes for the bot."""
        self._content_monitor = self._initialize_class(
            ContentMonitor,
            self._bot_config,
            self._session,
            self._game_updates_channel,
            self._esutaze_channel,
            self._alienware_arena_news_channel,
            self._user_kexo,
        )

        self._reddit_fetcher = self._initialize_class(
            RedditFetcher,
            self._bot_config,
            self._session,
            self._reddit_agent,
            self._free_stuff_channel,
            self._game_updates_channel,
        )
        self._sfd_servers = self._initialize_class(
            SFDServers, self._bot_config, self._session
        )
        self._lavalink_server_manager = self._initialize_class(
            LavalinkServerManager, self._session
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
            self._clear_cached_jokes()
            self._clear_temp_guild_data()
            await self._refresh_subreddit_icons()

        if now.hour % 5 == 0:
            self._clear_temp_reddit_data()

        if now.hour == 0:
            self._offline_lavalink_servers: list[str] = []
            self._load_humor_api_tokens()

        self.lavalink_servers = (
            await self._lavalink_server_manager.get_lavalink_servers(
                self._offline_lavalink_servers
            )
        )
        await self._content_monitor.power_outages()
        await self._content_monitor.contests()

    def _create_session(self) -> None:
        """Create a httpx session for the bot."""
        self._session = httpx.AsyncClient()
        self._session.headers = httpx.Headers({"User-Agent": UserAgent().random})
        print("Httpx session initialized.")

    async def connect_node(
        self, guild_id: int = KEXO_SERVER
    ) -> Optional[wavelink.Node]:
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
        Optional[wavelink.Node]
            The lavalink that was connected to.
        """
        if not self.lavalink_servers:
            print("No lavalink servers found.")
            return None

        if len(self.lavalink_servers) == 1:
            return self.lavalink_servers[0]

        for i in range(len(self.lavalink_servers)):
            node: wavelink.Node = await self.get_node(guild_id)
            if not node:
                return None

            try:
                await asyncio.wait_for(
                    wavelink.Pool.connect(nodes=[node], client=bot), timeout=2
                )
                # Some fucking nodes secretly don't respond,
                # I've played these games before!!!
                await node.fetch_info()

            except asyncio.TimeoutError:
                print(f"Node timed out. ({node.uri})")
                offline_lavalink_server = self.lavalink_servers.pop(i)
                self._offline_lavalink_servers.append(
                    urlparse(offline_lavalink_server.uri).hostname
                )
                continue
            except (
                wavelink.exceptions.LavalinkException,
                wavelink.exceptions.NodeException,
                aiohttp.client_exceptions.ServerDisconnectedError,
                aiohttp.client_exceptions.ClientConnectorError,
            ):
                print(f"Node failed to connect. ({node.uri})")
                offline_lavalink_server = self.lavalink_servers.pop(i)
                self._offline_lavalink_servers.append(
                    urlparse(offline_lavalink_server.uri).hostname
                )
                continue

            bot.node = node
            return node
        return None

    async def get_node(self, guild_id: int) -> wavelink.Node:
        """Get the next lavalink node, cycling is guild based.

        Parameters
        ----------
        guild_id: int
            The guild ID to get the node for.

        Returns
        -------
        wavelink.Node
            The lavalink node to use.
        """
        _, temp_guild_data = await get_guild_data(bot, guild_id)
        lavalink_server_pos = temp_guild_data["lavalink_server_pos"]

        lavalink_server_pos += 1
        if lavalink_server_pos >= len(self.lavalink_servers):
            lavalink_server_pos = 0

        temp_guild_data["lavalink_server_pos"] = lavalink_server_pos
        bot.temp_guild_data[guild_id] = temp_guild_data
        node: wavelink.Node = self.lavalink_servers[lavalink_server_pos]
        return node

    @staticmethod
    async def close_unused_nodes() -> None:
        """Clear unused lavalink nodes.

        This function will check if there are any lavalink nodes
        that are not being used and will close them.
        """
        nodes: list[wavelink.Node] = wavelink.Pool.nodes.values()
        for node in nodes:
            if len(wavelink.Pool.nodes) == 1:
                break

            if len(node.players) == 0:
                print(f"Node is empty, removing. ({node.uri})")
                # noinspection PyProtectedMember
                await node._pool_closer()  # Node is not properly closed
                await node.close(eject=True)

    @staticmethod
    def get_online_nodes() -> int:
        """Get the number of online lavalink nodes.

        Returns
        -------
        int
            The number of online lavalink nodes.
        """
        return len(
            [
                node
                for node in wavelink.Pool.nodes.values()
                if node.status == NodeStatus.CONNECTED
            ]
        )

    def get_avaiable_nodes(self) -> int:
        """Get the number of available lavalink nodes.

        Returns
        -------
        int
            The number of available lavalink nodes from Lavalink server manager.
        """
        return len(self.lavalink_servers)

    @staticmethod
    def _clear_temp_reddit_data() -> None:
        """Clear the temporary user reddit data."""
        for user_id in bot.temp_user_data:
            last_used = bot.temp_user_data[user_id]["reddit"]["last_used"]
            if not last_used:
                continue

            if is_older_than(5, last_used):
                bot.temp_user_data[user_id]["reddit"]["last_used"] = None
                bot.temp_user_data[user_id]["reddit"]["viewed_posts"] = set()
                bot.temp_user_data[user_id]["reddit"]["search_limit"] = 3

    @staticmethod
    def _clear_temp_guild_data() -> None:
        """Clear the temporary guild data."""
        for guild_id in bot.temp_guild_data:
            bot.temp_guild_data[guild_id] = generate_temp_guild_data()

    @staticmethod
    def _clear_cached_jokes() -> None:
        """Clear the cached jokes loaded from FunCommands"""
        bot.loaded_jokes = []
        bot.loaded_dad_jokes = []
        bot.loaded_yo_mama_jokes = []

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
                subreddit_icons[subreddit.display_name] = (
                    "https://www.pngkit.com/png/full/207-2074270_reddit-icon-png.png"
                )
                continue
            subreddit_icons[subreddit.display_name] = subreddit.icon_img

        print("Subreddit icons refreshed.")
        await self._bot_config.update_one(
            DB_CACHE, {"$set": {"subreddit_icons": subreddit_icons}}
        )

    async def _fetch_users(self) -> None:
        """Fetch users for the bot."""
        self._user_kexo = await bot.fetch_user(402221830930432000)
        print(f"User {self._user_kexo.name} fetched.")


kexobot = KexoBot()


def create_cog_session() -> None:
    """Create a httpx session for the cogs."""
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

    create_cog_session()
    for cog in cogs_list:
        bot.load_extension(f"cogs.{cog}")
    print("Cogs loaded.")


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


@bot.event
async def on_ready() -> None:
    """Event that runs when the bot is ready.
    This event is responsible for initializing the bot and
    connecting to the lavalink server.
    It also starts the main loop and the hourly loop.
    """
    print(f"Logged in as {bot.user}")

    await kexobot.initialize()
    main_loop_task.start()
    hourly_loop_task.start()

    while not kexobot.lavalink_servers:
        await asyncio.sleep(1)
    await kexobot.connect_node()
    print("Bot is ready.")


@bot.event
async def on_application_command_error(ctx: discord.ApplicationContext, error) -> None:
    """This event is called when an error occurs in an appliacation command.

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
            color=discord.Color.from_rgb(r=255, g=0, b=0),
        )
        embed.set_footer(text="Message will be deleted in 20 seconds.")
        await ctx.respond(embed=embed, ephemeral=True, delete_after=20)
        return

    if isinstance(error, commands.MissingPermissions):
        embed = discord.Embed(
            title="",
            description=f"🚫 You don't have the required permissions to use this command."
            f"\nRequired permissions: `{', '.join(error.missing_permissions)}`",
            color=discord.Color.from_rgb(r=255, g=0, b=0),
        )
        await ctx.respond(embed=embed, ephemeral=True)
        return

    if isinstance(error, commands.BotMissingPermissions):
        embed = discord.Embed(
            title="",
            description=f"🚫 I don't have the required permissions to use this command."
            f"\nRequired permissions: `{', '.join(error.missing_permissions)}`",
            color=discord.Color.from_rgb(r=255, g=0, b=0),
        )
        await ctx.send(embed=embed)
        return

    if isinstance(error, commands.BotMissingRole):
        embed = discord.Embed(
            title="",
            description=f"🚫 You don't have the required role to use this command."
            f"\nRequired role: `{error.missing_role}`",
            color=discord.Color.from_rgb(r=255, g=0, b=0),
        )
        await ctx.respond(embed=embed, ephemeral=True)
        return

    if isinstance(error, discord.errors.NotFound) and "Unknown interaction" in str(
        error
    ):
        embed = discord.Embed(
            title="",
            description="⚠️ Discord API is not responding. Please try again in a minute.",
            color=discord.Color.from_rgb(r=255, g=165, b=0),
        )
        try:
            await ctx.channel.send(embed=embed, delete_after=20)
        except discord.Forbidden:
            pass
        return

    raise error


@bot.event
async def on_guild_join(guild: discord.Guild) -> None:
    """Event that runs when the bot joins a new guild.
    This event is responsible for creating the guild data in the database.

    Parameters
    ----------
    guild: discord.Guild
        The guild that the bot joined.
    """
    print(f"Joined new guild: {guild.name}")


bot.run(DISCORD_TOKEN)
