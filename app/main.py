import discord
import asyncpraw
import httpx
import dns.resolver
import random
import wavelink
import asyncio

from fake_useragent import UserAgent
from discord.ext import tasks, commands
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from wavelink.exceptions import LavalinkException

from constants import (
    DISCORD_TOKEN,
    MONGO_DB_URL,
    REDDIT_PASSWORD,
    REDDIT_SECRET,
    REDDIT_USER_AGENT,
    REDDIT_USERNAME,
    REDDIT_CLIENT_ID,
    HUMOR_SECRET,
    CLEAR_CACHE_HOUR,
    DB_REDDIT_CACHE,
    ESUTAZE_CHANNEL,
    GAME_UPDATES_CHANNEL,
    FREE_STUFF_CHANNEL,
)
from utils import return_dict

from classes.Esutaze import Esutaze
from classes.OnlineFix import OnlineFix
from classes.Game3rb import Game3rb
from classes.AlienwareArena import AlienwareArena
from classes.LavalinkServerFetch import LavalinkServerFetch
from classes.ElektrinaVypadky import ElektrinaVypadky
from classes.RedditCrackWatch import RedditCrackWatch
from classes.RedditFreegamefindings import RedditFreeGameFindings
from classes.Fanatical import Fanatical
from classes.SFDServers import SFDServers

dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ["8.8.8.8"]

bot = discord.Bot()


# TODO: Make Game3rb more readable
# TODO: Redo Reddit DB


class KexoBOT:
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
        self.which_lavalink_server = -1
        self.lavalink_servers = []
        self.main_loop_counter = 0
        self.database = AsyncIOMotorClient(MONGO_DB_URL)["KexoBOTDatabase"][
            "KexoBOTCollection"
        ]

        self.reddit = asyncpraw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_SECRET,
            user_agent=REDDIT_USER_AGENT,
            username=REDDIT_USERNAME,
            password=REDDIT_PASSWORD,
        )

        # Attach bot, so we can use it in cogs
        bot.database = self.database
        bot.reddit = self.reddit
        bot.connect_node = self.connect_node
        bot.get_node = self.get_node

        self.onlinefix = None | OnlineFix
        self.game3rb = None | Game3rb
        self.reddit_freegamefindings = None | RedditFreeGameFindings
        self.reddit_crackwatch = None | RedditCrackWatch
        self.elektrina_vypadky = None | ElektrinaVypadky
        self.esutaze = None | Esutaze
        self.lavalink_fetch = None | LavalinkServerFetch
        self.fanatical = None | Fanatical
        self.sfd_servers = None | SFDServers
        self.alienwarearena = None | AlienwareArena
        self.esutaze_channel = None | discord.TextChannel
        self.game_updates_channel = None | discord.TextChannel
        self.free_stuff_channel = None | discord.TextChannel

    async def initialize(self) -> None:
        """Initialize the bot and fetch all channels and users."""

        await self._fetch_users()
        await self.create_session()
        await self._fetch_channels()
        await self._define_classes()
        await self._generate_graphs()
        bot.subbredit_cache = return_dict(
            await self.database.find_one(DB_REDDIT_CACHE, {"_id": False})
        )
        bot.sfd_servers = self.sfd_servers

    @staticmethod
    async def _fetch_channel(channel_id: int) -> discord.TextChannel:
        """Helper to fetch a channel by ID."""

        return await bot.fetch_channel(channel_id)

    @staticmethod
    async def _initialize_class(cls, *args):
        """Helper to initialize a class with arguments."""

        return cls(*args)

    async def _fetch_channels(self) -> None:
        """Fetch all channels for the bot."""

        self.esutaze_channel = await self._fetch_channel(ESUTAZE_CHANNEL)
        self.game_updates_channel = await self._fetch_channel(GAME_UPDATES_CHANNEL)
        self.free_stuff_channel = await self._fetch_channel(FREE_STUFF_CHANNEL)
        print("Channels fetched.")

    async def _generate_graphs(self, log: bool = True) -> None:
        """Generate graphs for the bot."""

        await self.sfd_servers.generate_graph_day("New_York")
        await self.sfd_servers.generate_graph_week("New_York")
        if not log:
            return
        print("Graphs generated.")

    async def _define_classes(self) -> None:
        """Define classes for the bot."""

        self.onlinefix = await self._initialize_class(
            OnlineFix, self.database, self.session,  self.game_updates_channel
        )
        self.game3rb = await self._initialize_class(
            Game3rb, self.database, self.session,  self.game_updates_channel
        )
        self.alienwarearena = await self._initialize_class(
            AlienwareArena, self.database, self.session, self.free_stuff_channel
        )
        self.fanatical = await self._initialize_class(
            Fanatical, self.database, self.session, self.free_stuff_channel
        )
        self.reddit_freegamefindings = await self._initialize_class(
            RedditFreeGameFindings,
            self.database,
            self.session,
            self.reddit,
            self.free_stuff_channel,
        )
        self.sfd_servers = await self._initialize_class(
            SFDServers, self.database, self.session
        )
        self.reddit_crackwatch = await self._initialize_class(
            RedditCrackWatch,
            self.database,
            self.reddit,
            self.game_updates_channel,
            self.user_kexo,
        )
        self.elektrina_vypadky = await self._initialize_class(
            ElektrinaVypadky, self.database, self.session, self.user_kexo
        )
        self.esutaze = await self._initialize_class(
            Esutaze, self.database, self.session, self.esutaze_channel
        )
        self.lavalink_fetch = await self._initialize_class(
            LavalinkServerFetch,  self.session
        )

    async def create_session(self) -> None:
        """Create a httpx session for the bot."""

        self.session = httpx.AsyncClient()
        self.session.headers = httpx.Headers({"User-Agent": UserAgent().random})
        print("Httpx session initialized.")

    async def connect_node(self) -> None:
        """Connect to lavalink node."""

        if not self.lavalink_servers:
            print("No lavalink servers found.")
            return

        for _ in range(len(self.lavalink_servers)):
            node: wavelink.Node = await self.get_node()
            if not node:
                return

            try:
                await asyncio.wait_for(
                    wavelink.Pool.connect(nodes=node, client=bot), timeout=5
                )
            except asyncio.TimeoutError:
                print(f"Node {node.uri} is not ready, trying next...")
                continue

            bot.node = node
            return

    async def get_node(self) -> wavelink.Node:
        """Get the next lavalink node."""

        if not self.lavalink_servers:
            print("No lavalink servers found.")
            return None

        self.which_lavalink_server += 1
        if self.which_lavalink_server >= len(self.lavalink_servers):
            self.which_lavalink_server = 0

        ip: str = self.lavalink_servers[self.which_lavalink_server]["ip"]
        password: str = self.lavalink_servers[self.which_lavalink_server]["password"]
        print(f"Cycling through lavalink servers: {ip}")

        node = [
            wavelink.Node(
                uri=ip,
                password=password,
                retries=1,
                inactive_player_timeout=600
            )
        ]

        return node

    async def set_joke(self) -> None:
        """Set a random joke as the bot's activity."""

        joke_categroy = random.choice(("jewish", "racist"))
        try:
            joke = await self.session.get(
                f"https://api.humorapi.com/jokes/random?max-length=128&include-tags="
                f"{joke_categroy}&api-key={HUMOR_SECRET}"
            )
        except httpx.ReadTimeout:
            print("Couldn't fetch joke: Timeout")
            return

        joke = joke.json().get("joke")
        await bot.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name=joke)
        )

    async def _fetch_users(self) -> None:
        """Fetch users for the bot."""

        self.user_kexo = await bot.fetch_user(402221830930432000)
        print(f"User {self.user_kexo.name} fetched.")

    async def update_reddit_cache(self, now: datetime) -> None:
        """Update the reddit cache in the database."""

        update = {}
        for guild_id, cache in bot.subbredit_cache.items():
            # If midnight, set search_level to 0
            to_upload = [
                "0" if now.hour == CLEAR_CACHE_HOUR else str(cache["search_level"]),
                str(cache.get("nsfw")),
                cache.get("urls"),
                str(cache.get("which_subreddit")),
            ]
            # Remove urls at midnight
            reddit_urls = [
                reddit_url
                for reddit_url in to_upload[2].split("\n")
                if not reddit_url or reddit_url.split("*")[1] != str(now.hour)
            ]
            to_upload[2] = "\n".join(reddit_urls)
            update[guild_id] = ",".join(to_upload)

        await self.database.update_many(DB_REDDIT_CACHE, {"$set": update})
        bot.subbredit_cache = return_dict(update)

    async def main_loop(self) -> None:
        """Main loop for the bot.
        This loop runs every minute and runs the different classes that
        fetch data from different sources.
        It runs the classes in a round-robin fashion.
        """
        await self.reddit_crackwatch.run()
        now = datetime.now()
        if self.main_loop_counter == 0:
            self.main_loop_counter = 1
            await self.reddit_freegamefindings.run()

        elif self.main_loop_counter == 1:
            self.main_loop_counter = 2
            await self.alienwarearena.run()

        elif self.main_loop_counter == 2:
            self.main_loop_counter = 3
            await self.game3rb.run()

        elif self.main_loop_counter == 3:
            self.main_loop_counter = 4
            await self.onlinefix.run()

        elif self.main_loop_counter == 4:
            self.main_loop_counter = 5
            await self.reddit_crackwatch.run()

        elif self.main_loop_counter == 5:
            self.main_loop_counter = 6
            await self.fanatical.run()

        elif self.main_loop_counter == 6:
            self.main_loop_counter = 0
            await self.esutaze.run()

        if now.minute % 6 == 0:
            await self.sfd_servers.update_stats()

    async def hourly_loop(self) -> None:
        """Hourly loop for the bot.
        This loop runs every hour and runs the different classes that
        fetch data from different sources.
        It runs the classes in a round-robin fashion.
        It also updates the reddit cache and fetches lavalink servers.
        """

        now = datetime.now()

        if now.hour == 0:
            await self.set_joke()

        self.lavalink_servers = await self.lavalink_fetch.get_lavalink_servers()
        await self.update_reddit_cache(now)
        await self.elektrina_vypadky.run()


kexobot = KexoBOT()


def create_cog_session() -> None:
    """Create a httpx session for the cogs."""

    bot.session = httpx.AsyncClient()
    bot.session.headers = httpx.Headers({"User-Agent": UserAgent().random})


def setup_cogs() -> None:
    """Load all cogs for the bot."""

    create_cog_session()
    bot.load_extension("cogs.Play")
    bot.load_extension("cogs.Listeners")
    bot.load_extension("cogs.Queue")
    bot.load_extension("cogs.Audio")
    bot.load_extension("cogs.FunStuff")
    bot.load_extension("cogs.Commands")
    print("Cogs loaded.")


setup_cogs()


@tasks.loop(minutes=2)
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
async def on_command_error(ctx: discord.ApplicationContext, error) -> None:
    """Event that runs when a command raises an error.
    This event is responsible for handling the error and
    sending an error message to the user.
    It also handles the case when the command is not found.
    """
    if isinstance(error, commands.errors.CommandNotFound):
        embed = discord.Embed(
            title="",
            description=f"🚫 This command doesn't exist.",
            color=discord.Color.from_rgb(r=255, g=0, b=0),
        )
        embed.set_footer(text="Message will be deleted in 20 seconds.")
        await ctx.send(embed=embed, delete_after=20)


@bot.event
async def on_application_command_error(ctx: discord.ApplicationContext, error) -> None:
    """Event that runs when a command is timed out."""
    if isinstance(error, commands.CommandOnCooldown):
        error_str = str(error).split()
        embed = discord.Embed(
            title="",
            description=f"🚫 You're sending too much!, try again in `{error_str[7]}`.",
            color=discord.Color.from_rgb(r=255, g=0, b=0),
        )
        embed.set_footer(text="Message will be deleted in 20 seconds.")
        await ctx.respond(embed=embed, ephemeral=True, delete_after=20)
        return
    elif isinstance(error, LavalinkException):
        vc: wavelink.Player = ctx.voice_client
        if not vc:
            raise error

        await ctx.respond(
            embed=discord.Embed(
                title="",
                description="There was an error processing your request, trying to recconnect node.",
                color=discord.Color.from_rgb(r=255, g=0, b=0),
            )
        )
        node: wavelink.Node = await kexobot.get_node()
        await vc.switch_node(node)
    raise error


bot.run(DISCORD_TOKEN)
