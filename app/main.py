import asyncio
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

from app.classes.contests import ContestMonitor
from app.classes.game_updates import GameUpdates
from app.classes.lavalink_server import LavalinkServerManager
from app.classes.power_outages import PowerOutageMonitor
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
    KEXO_SERVER,
)
from app.utils import generate_temp_guild_data, is_older_than

dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ["8.8.8.8"]

bot = Bot()


class KexoBot:
    """Main class for the bot.
    This class is responsible for initializing the bot, creating the session,
    and connecting to the lavalink server.
    It also contains the main loop and the hourly loop.
    The main loop is responsible for running the different classes that
    fetch data from different sources.
    The hourly loop is responsible for updating the reddit cache and
    fetching lavalink servers.
    """

    def __init__(self):
        self.user_kexo = None | discord.User
        self.session = None | httpx.AsyncClient
        self.subreddit_cache = None | dict
        self.main_loop_counter = 0
        self.lavalink_servers: list[wavelink.Node] = []
        self.offline_lavalink_servers: list[str] = []
        self.guild_temp_data = {}

        database = AsyncIOMotorClient(MONGO_DB_URL)["KexoBOTDatabase"]
        self.bot_config = database["BotConfig"]
        self.user_data_db = database["UserData"]
        self.guild_data_db = database["GuildData"]

        self.reddit_agent = asyncpraw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_SECRET,
            user_agent=REDDIT_USER_AGENT,
            username=REDDIT_USERNAME,
            password=REDDIT_PASSWORD,
        )

        # Attach bot, so we can use it in cogs
        # Database
        bot.user_data = {}
        bot.temp_user_data = {}
        bot.bot_config = self.bot_config
        bot.user_data_db = self.user_data_db
        bot.guild_data_db = self.guild_data_db
        # Functions
        bot.reddit_agent = self.reddit_agent
        bot.connect_node = self.connect_node
        bot.close_unused_nodes = self.close_unused_nodes
        bot.get_online_nodes = self.get_online_nodes
        bot.get_avaiable_nodes = self.get_avaiable_nodes
        bot.guild_temp_data = self.guild_temp_data
        # Other
        bot.humor_api_exahusted = False

        # Initialize class variables
        self.reddit_fetcher = None | RedditFetcher
        self.power_outage_monitor = None | PowerOutageMonitor
        self.contest_monitor = None | ContestMonitor
        self.lavalink_server_manager = None | LavalinkServerManager
        self.sfd_servers = None | SFDServers
        self.game_updates = None | GameUpdates
        self.esutaze_channel = None | discord.TextChannel
        self.game_updates_channel = None | discord.TextChannel
        self.free_stuff_channel = None | discord.TextChannel

    async def initialize(self) -> None:
        """Initialize the bot and fetch all channels and users."""
        await self._fetch_users()
        await self._fetch_channels()
        await self._fetch_subreddit_icons()
        self._create_session()
        self._define_classes()
        bot.sfd_servers = self.sfd_servers

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
        self.esutaze_channel = await self._fetch_channel(ESUTAZE_CHANNEL)
        self.game_updates_channel = await self._fetch_channel(GAME_UPDATES_CHANNEL)
        self.free_stuff_channel = await self._fetch_channel(FREE_STUFF_CHANNEL)
        print("Channels fetched.")

    async def _fetch_subreddit_icons(self) -> None:
        """Fetch subreddit icons for the bot."""
        subreddit_icons = await self.bot_config.find_one(DB_CACHE)
        bot.subreddit_icons = subreddit_icons["subreddit_icons"]
        print("Subreddit icons fetched.")

    def _define_classes(self) -> None:
        """Define classes for the bot."""
        # Initialize the new GameUpdates class
        self.game_updates = self._initialize_class(
            GameUpdates,
            self.bot_config,
            self.session,
            self.game_updates_channel,
            self.user_kexo,
        )

        # Keep the original classes for now until we verify the new one works
        self.reddit_fetcher = self._initialize_class(
            RedditFetcher,
            self.bot_config,
            self.session,
            self.reddit_agent,
            self.free_stuff_channel,
            self.game_updates_channel,
        )
        self.sfd_servers = self._initialize_class(
            SFDServers, self.bot_config, self.session
        )
        self.power_outage_monitor = self._initialize_class(
            PowerOutageMonitor, self.bot_config, self.session, self.user_kexo
        )
        self.contest_monitor = self._initialize_class(
            ContestMonitor, self.bot_config, self.session, self.esutaze_channel
        )
        self.lavalink_server_manager = self._initialize_class(
            LavalinkServerManager, self.session
        )

    async def main_loop(self) -> None:
        """Main loop for the bot.
        This loop runs every minute and runs the different classes that
        fetch data from different sources.
        It runs the classes in a round-robin fashion.
        """
        now = datetime.now(ZoneInfo("Europe/Bratislava"))
        if self.main_loop_counter == 0:
            self.main_loop_counter = 1
            await self.reddit_fetcher.freegamefindings()

        elif self.main_loop_counter == 1:
            self.main_loop_counter = 2
            await self.game_updates.alienware_arena()

        elif self.main_loop_counter == 2:
            self.main_loop_counter = 3
            await self.game_updates.game3rb()

        elif self.main_loop_counter == 3:
            self.main_loop_counter = 4
            await self.game_updates.online_fix()

        elif self.main_loop_counter == 4:
            self.main_loop_counter = 5
            await self.reddit_fetcher.crackwatch()

        elif self.main_loop_counter == 5:
            self.main_loop_counter = 6
            await self.game_updates.fanatical()

        elif self.main_loop_counter == 6:
            self.main_loop_counter = 0
            await self.contest_monitor.run()

        if now.minute % 6 == 0:
            await self.sfd_servers.update_stats(now)

    async def hourly_loop(self) -> None:
        """Hourly loop for the bot.
        This loop runs every hour and runs the different classes that
        fetch data from different sources.
        It runs the classes in a round-robin fashion.
        It also updates the reddit cache and fetches lavalink servers.
        """
        now = datetime.now(ZoneInfo("Europe/Bratislava"))
        if now.day == 6 and now.hour == 0:
            await self._refresh_subreddit_icons()

        if now.hour % 5 == 0:
            self._clear_temp_reddit_data()

        if now.hour == 0:
            self.bot.humor_api_exahusted = False
            self._clear_offline_lavalink_servers()

        self.lavalink_servers = await self.lavalink_server_manager.get_lavalink_servers(
            self.offline_lavalink_servers
        )
        await self.power_outage_monitor.run()

    def _create_session(self) -> None:
        """Create a httpx session for the bot."""
        self.session = httpx.AsyncClient()
        self.session.headers = httpx.Headers({"User-Agent": UserAgent().random})
        print("Httpx session initialized.")

    async def connect_node(
        self, guild_id: int = KEXO_SERVER
    ) -> Optional[wavelink.Node]:
        """Connect to lavalink node."""
        if not self.lavalink_servers:
            print("No lavalink servers found.")
            return None

        if len(self.lavalink_servers) == 1:
            return self.lavalink_servers[0]

        for i in range(len(self.lavalink_servers)):
            node: wavelink.Node = self.get_node(guild_id)
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
                self.offline_lavalink_servers.append(
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
                self.offline_lavalink_servers.append(
                    urlparse(offline_lavalink_server.uri).hostname
                )
                continue

            bot.node = node
            return node
        return None

    def get_node(self, guild_id: int) -> wavelink.Node:
        """Get the next lavalink node, cycling is guild based."""
        lavalink_server_pos = self.guild_temp_data.get(guild_id)
        if not lavalink_server_pos:
            self.guild_temp_data[guild_id] = generate_temp_guild_data()
        lavalink_server_pos = self.guild_temp_data[guild_id]["lavalink_server_pos"]

        lavalink_server_pos += 1
        if lavalink_server_pos >= len(self.lavalink_servers):
            lavalink_server_pos = 0

        self.guild_temp_data[guild_id]["lavalink_server_pos"] = lavalink_server_pos
        node: wavelink.Node = self.lavalink_servers[lavalink_server_pos]
        return node

    @staticmethod
    async def close_unused_nodes() -> None:
        """Clear unused lavalink nodes."""
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
        """Get the number of online lavalink nodes."""
        return len(
            [
                node
                for node in wavelink.Pool.nodes.values()
                if node.status == NodeStatus.CONNECTED
            ]
        )

    def get_avaiable_nodes(self) -> int:
        """Get the number of available lavalink nodes."""
        return len(self.lavalink_servers)

    def _clear_offline_lavalink_servers(self) -> None:
        """Clear offline lavalink servers."""
        self.offline_lavalink_servers: list[str] = []

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

    async def _refresh_subreddit_icons(self) -> None:
        """Refreshes subreddit icons on Sunday."""
        subreddit_icons = {}
        for subreddit_name in SHITPOST_SUBREDDITS_ALL:
            subreddit: asyncpraw.models.Subreddit = await self.reddit_agent.subreddit(
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
        await self.bot_config.update_one(
            DB_CACHE, {"$set": {"subreddit_icons": subreddit_icons}}
        )

    async def _fetch_users(self) -> None:
        """Fetch users for the bot."""
        self.user_kexo = await bot.fetch_user(402221830930432000)
        print(f"User {self.user_kexo.name} fetched.")


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
    await kexobot.main_loop()


@tasks.loop(hours=1)
async def hourly_loop_task() -> None:
    await kexobot.hourly_loop()


@main_loop_task.before_loop
async def before_main_loop() -> None:
    await bot.wait_until_ready()


@hourly_loop_task.before_loop
async def before_hourly_loop() -> None:
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
    """This event is called when an error occurs in an appliacation command."""
    if isinstance(error, commands.CommandOnCooldown):
        embed = discord.Embed(
            title="",
            description=f"🚫 You're sending too much!, try again in `{round(error.retry_after, 1)}s`.",
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
    """
    print(f"Joined new guild: {guild.name}")


bot.run(DISCORD_TOKEN)
