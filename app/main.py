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
from pymongo import AsyncMongoClient
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
    REDDIT_ICON,
    WORDNIK_API_KEY,
    WORDNIK_API_URL,
)
from app.utils import (
    get_guild_data,
    is_older_than,
    generate_temp_guild_data,
    make_http_request,
)

dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ["8.8.8.8"]

bot = Bot()


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
        self.lavalink_servers: list[wavelink.Node] = []
        self.session = None | httpx.AsyncClient

        self._user_kexo = None | discord.User
        self._subreddit_cache = None | dict
        self._hostname = socket.gethostname()
        self._main_loop_counter = 0
        self._offline_lavalink_servers: list[str] = []

        database = AsyncMongoClient(MONGO_DB_URL)["KexoBOTDatabase"]
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

        self._reddit_fetcher = None | RedditFetcher
        self._content_monitor = None | ContentMonitor
        self._lavalink_server_manager = None | LavalinkServerManager
        self._sfd_servers = None | SFDServers

        self._channel_esutaze = None | discord.TextChannel
        self._channel_game_updates = None | discord.TextChannel
        self._channel_free_stuff = None | discord.TextChannel
        self._channel_alienware_arena_news = None | discord.TextChannel

        # Attach to bot, so we can use it in cogs
        bot.user_data = {}
        bot.temp_user_data = {}
        bot.guild_data = {}
        bot.temp_guild_data = {}
        bot.bot_config = self._bot_config
        bot.user_data_db = self._user_data_db
        bot.guild_data_db = self._guild_data_db

        bot.reddit_agent = self._reddit_agent
        bot.connect_node = self.connect_node
        bot.close_unused_nodes = self.close_unused_nodes
        bot.get_online_nodes = self.get_online_nodes
        bot.get_avaiable_nodes = self.get_avaiable_nodes

        bot.humor_api_tokens = {}
        bot.loaded_jokes = []
        bot.loaded_dad_jokes = []
        bot.loaded_yo_mama_jokes = []

    async def initialize(self) -> None:
        """Initialize the _bot and fetch all channels and users."""
        await self._fetch_users()
        await self._fetch_channels()
        await self._fetch_subreddit_icons()
        self._load_humor_api_tokens()
        self._create_session()
        self._define_classes()

    async def _fetch_channels(self) -> None:
        """Fetch all channels for the bot."""
        self._channel_esutaze = await self._fetch_channel(ESUTAZE_CHANNEL)
        self._channel_game_updates = await self._fetch_channel(GAME_UPDATES_CHANNEL)
        self._channel_free_stuff = await self._fetch_channel(FREE_STUFF_CHANNEL)
        self._channel_alienware_arena_news = await self._fetch_channel(
            ALIENWARE_ARENA_NEWS_CHANNEL
        )
        print("Channels fetched.")

    async def _fetch_subreddit_icons(self) -> None:
        """Fetch subreddit icons for the bot."""
        subreddit_icons = await self._bot_config.find_one(DB_CACHE)
        bot.subreddit_icons = subreddit_icons["subreddit_icons"]
        print("Subreddit icons fetched.")

    def _define_classes(self) -> None:
        """Define classes for the bot."""
        self._content_monitor = self._initialize_class(
            ContentMonitor,
            self._bot_config,
            self.session,
            self._channel_game_updates,
            self._channel_esutaze,
            self._channel_alienware_arena_news,
            self._user_kexo,
        )

        self._reddit_fetcher = self._initialize_class(
            RedditFetcher,
            self._bot_config,
            self.session,
            self._reddit_agent,
            self._channel_free_stuff,
            self._channel_game_updates,
        )
        self._sfd_servers = self._initialize_class(
            SFDServers, self._bot_config, self.session
        )
        self._lavalink_server_manager = self._initialize_class(
            LavalinkServerManager, self.session
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

        if now.hour % 6 == 0:
            self._clear_temp_reddit_data()

        if now.hour == 0:
            self._load_humor_api_tokens()

        if now.hour == 4:
            await self.wordnik_presence()

        if now.day % 2 == 0 and now.hour == 0:
            self._offline_lavalink_servers = []

        self.lavalink_servers = (
            await self._lavalink_server_manager.get_lavalink_servers()
        )
        await self._content_monitor.power_outages()
        await self._content_monitor.contests()

    async def connect_node(
        self, guild_id: int = KEXO_SERVER, offline_node: str = None
    ) -> Optional[wavelink.Node]:
        """Connect to lavalink node.

        This function will try to connect to the lavalink node
        and if it fails, it will try to connect to the next node.
        If all nodes fail, it will return None.

        Parameters
        ----------
        guild_id: int
            The guild ID to connect to.
        offline_node: str
            The node to remove from the list of nodes.

        Returns
        -------
        Optional[wavelink.Node]
            The lavalink that was connected to.
        """
        if not self.lavalink_servers:
            # If somehow all nodes are offline, reset the list of offline nodes
            self._offline_lavalink_servers = []
            self.lavalink_servers = (
                await self._lavalink_server_manager.get_lavalink_servers(
                    self._offline_lavalink_servers
                )
            )
            if not self.lavalink_servers:
                print("No lavalink servers found.")
                return None

        if len(self.lavalink_servers) == 1:
            return self.lavalink_servers[0]

        if offline_node:
            self._remove_node(offline_node)

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
                self._remove_node(self.lavalink_servers[i].uri)
                continue
            except (
                wavelink.exceptions.LavalinkException,
                wavelink.exceptions.NodeException,
                aiohttp.client_exceptions.ServerDisconnectedError,
                aiohttp.client_exceptions.ClientConnectorError,
                AttributeError,
            ):
                print(f"Node failed to connect. ({node.uri})")
                self._remove_node(self.lavalink_servers[i].uri)
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

    async def wordnik_presence(self) -> None:
        """Fetches the word of the day from Wordnik API."""
        url = WORDNIK_API_URL + WORDNIK_API_KEY
        json_data = await make_http_request(self.session, url, get_json=True)
        if not json_data:
            print("Wordnik API returned no data.")
            return

        word = json_data["word"]
        definition = json_data["definitions"][0]["text"]
        definition = definition[:-1]
        presence = f"{word}: {definition}"

        if len(presence) > 128:
            print("Presence too long, skipping.")
            return

        activity = discord.Activity(type=discord.ActivityType.watching, name=presence)
        await bot.change_presence(status=discord.Status.online, activity=activity)
        print(f"Presence set to: {word}")

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
                subreddit_icons[subreddit.display_name] = REDDIT_ICON
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

    def _create_session(self) -> None:
        """Create a httpx session for the bot."""
        self.session = httpx.AsyncClient()
        self.session.headers = httpx.Headers({"User-Agent": UserAgent().random})
        print("Httpx session initialized.")

    def _remove_node(self, node_uri: str) -> str:
        """Remove a lavalink node from the list of nodes.

        Parameters
        ----------
        node_uri: str
            The uri of the node to remove.

        Returns
        -------
        str
            The uri of the node that was removed.
        """
        for node in self.lavalink_servers:
            if node.uri == node_uri:
                self.lavalink_servers.remove(node)
                break

        self._offline_lavalink_servers.append(urlparse(node_uri).hostname)
        return node_uri

    @staticmethod
    def _load_humor_api_tokens() -> None:
        """Load the humor API tokens."""
        bot.humor_api_tokens = {}
        for token in HUMOR_API_SECRET:
            bot.humor_api_tokens[token] = {
                "exhausted": False,
            }

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
    async def _fetch_channel(channel_id: int) -> discord.TextChannel:
        """Helper to fetch a channel by ID, returns :class:`discord.TextChannel`.

        Parameters
        ----------
        channel_id: int
            The ID of the channel to fetch.
        """
        return await bot.fetch_channel(channel_id)

    @staticmethod
    def _initialize_class(cls, *args) -> object:
        """Helper to initialize a class with arguments.

        Parameters
        ----------
        cls: type
            The class to initialize.
        *args: tuple
            The arguments to pass to the class.
        """
        return cls(*args)

    @staticmethod
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

    def get_avaiable_nodes(self) -> int:
        """Get the number of available lavalink nodes,
        returns ``int`` of available nodes.
        """
        return len(self.lavalink_servers)

    @staticmethod
    def _clear_temp_reddit_data() -> None:
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

    while not main.lavalink_servers:
        await asyncio.sleep(1)
    await main.connect_node()

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
    print(f"Logged in as {bot.user}")
    await bot_loader(kexobot)
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
    """Event that runs when the bot joins a new guild.
    This event is responsible for creating the guild data in the database.

    Parameters
    ----------
    guild: :class:`discord.Guild`
        The guild that the bot joined.
    """
    print(f"Joined new guild: {guild.name}")


bot.run(DISCORD_TOKEN)
