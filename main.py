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

from constants import DISCORD_TOKEN, MONGO_DB_URL, REDDIT_PASSWORD, REDDIT_SECRET, REDDIT_USER_AGENT, REDDIT_USERNAME, \
    REDDIT_CLIENT_ID, HUMOR_SECRET, CLEAR_CACHE_HOUR, DB_REDDIT_CACHE, ESUTAZE_CHANNEL, GAME_UPDATES_CHANNEL, \
    FREE_STUFF_CHANNEL
from utils import return_dict

from classes.Esutaze import Esutaze
from classes.OnlineFix import OnlineFix
from classes.Game3rb import Game3rb
from classes.AlienwareArena import AlienwareArena
from classes.LavalinkServerFetch import LavalinkServerFetch
from classes.ElektrinaVypadky import ElektrinaVypadky
from classes.RedditCrackWatch import RedditCrackWatch
from classes.RedditFreegamefindings import RedditFreeGameFindings

dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ["8.8.8.8"]

bot = discord.Bot()


# TODO: Rewrite Game3rb
# TODO: Rewrite Queue cog, fix queue length

class KexoBOT:
    def __init__(self):
        self.user_kexo = None
        self.session = None
        self.which_lavalink_server = -1
        self.lavalink_servers = []
        self.main_loop_counter = 0
        self.database = AsyncIOMotorClient(MONGO_DB_URL)["KexoBOTDatabase"]["KexoBOTCollection"]

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

        self.onlinefix = None
        self.game3rb = None
        self.reddit_freegamefindings = None
        self.reddit_crackwatch = None
        self.elektrina_vypadky = None
        self.esutaze = None

    async def initialize(self) -> None:
        await self._fetch_users()
        await self.create_session()
        await self._fetch_channels()

        bot.subbredit_cache = return_dict(
            await self.database.find_one(DB_REDDIT_CACHE, {"_id": False}))
        await self._define_classes()

    async def _fetch_channels(self) -> None:
        self.esutaze_channel = await bot.fetch_channel(ESUTAZE_CHANNEL)
        self.game_updates_channel = await bot.fetch_channel(GAME_UPDATES_CHANNEL)
        self.free_stuff_channel = await bot.fetch_channel(FREE_STUFF_CHANNEL)
        print("Channels fetched.")

    async def _define_classes(self) -> None:
        self.onlinefix = OnlineFix(self.session, self.database, self.game_updates_channel)
        self.game3rb = Game3rb(self.session, self.database, self.game_updates_channel)
        self.alienwarearena = AlienwareArena(self.database, self.session, self.free_stuff_channel)
        self.reddit_freegamefindings = RedditFreeGameFindings(self.database, self.reddit,
                                                              self.session, self.free_stuff_channel)
        self.reddit_crackwatch = RedditCrackWatch(self.database, self.reddit,
                                                  self.game_updates_channel, self.user_kexo)
        self.elektrina_vypadky = ElektrinaVypadky(self.session, self.database, self.user_kexo)
        self.esutaze = Esutaze(self.session, self.database, self.esutaze_channel)
        self.lavalink_fetch = LavalinkServerFetch(bot, self.session)
        print("Classes defined.")

    async def create_session(self) -> None:
        self.session = httpx.AsyncClient()
        self.session.verify = True
        self.session.headers = {"User-Agent": UserAgent().random}
        print("Httpx session initialized.")

    async def connect_node(self) -> None:
        if not self.lavalink_servers:
            print("No lavalink servers found.")
            return

        for _ in range(len(self.lavalink_servers)):
            self.which_lavalink_server += 1
            if self.which_lavalink_server >= len(self.lavalink_servers):
                self.which_lavalink_server = 0

            ip = self.lavalink_servers[self.which_lavalink_server]["ip"]
            password = self.lavalink_servers[self.which_lavalink_server]["password"]
            print(f"Server {ip} fetched, testing connection...")

            node = [
                wavelink.Node(uri=ip, password=password, retries=1, resume_timeout=0, inactive_player_timeout=600)]

            try:
                await asyncio.wait_for(wavelink.Pool.connect(nodes=node, client=bot), timeout=5)
            except asyncio.TimeoutError:
                print(f"Node {ip} is not ready, trying next...")
                continue

            bot.node = node
            return

    async def set_joke(self) -> None:
        # insults, dark
        joke_categroy = random.choice(("jewish", "racist"))
        joke = await self.session.get(
            f"https://api.humorapi.com/jokes/random?max-length=128&include-tags="
            f"{joke_categroy}&api-key={HUMOR_SECRET}").json().get("joke")
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=joke))

    async def _fetch_users(self) -> None:
        self.user_kexo = await bot.fetch_user(402221830930432000)
        print(f"User {self.user_kexo.name} fetched.")

    async def update_reddit_cache(self, now: datetime) -> None:
        update = {}
        for guild_id, cache in bot.subbredit_cache.items():
            # If midnight, set search_level to 0
            to_upload = ["0" if now.hour == CLEAR_CACHE_HOUR else str(cache["search_level"]),
                         str(cache.get("nsfw")),
                         cache.get("urls"),
                         str(cache.get("which_subreddit"))]
            # Remove urls at midnight
            reddit_urls = [reddit_url for reddit_url in to_upload[2].split("\n") if
                           not reddit_url or reddit_url.split("*")[1] != str(now.hour)]
            to_upload[2] = "\n".join(reddit_urls)
            update[guild_id] = ",".join(to_upload)

        await self.database.update_many(DB_REDDIT_CACHE, {"$set": update})
        bot.subbredit_cache = return_dict(update)

    async def main_loop(self) -> None:
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
            self.main_loop_counter = 0
            await self.esutaze.run()

    async def hourly_loop(self) -> None:
        now = datetime.now()

        if now.hour == 0:
            await self.set_joke()

        self.lavalink_servers = await self.lavalink_fetch.get_lavalink_servers()
        await self.update_reddit_cache(now)
        await self.elektrina_vypadky.run()


kexobot = KexoBOT()


def create_cog_session() -> None:
    bot.session = httpx.AsyncClient()
    bot.session.verify = True
    bot.session.headers = {"User-Agent": UserAgent().random}


def setup_cogs() -> None:
    create_cog_session()
    bot.load_extension("cogs.Play")
    bot.load_extension("cogs.Listeners")
    bot.load_extension("cogs.Queue")
    bot.load_extension("cogs.Audio")
    bot.load_extension("cogs.Disconnect")
    bot.load_extension("cogs.FunStuff")
    bot.load_extension("cogs.Commands")
    bot.load_extension("cogs.DatabaseManager")
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
    print(f"Logged in as {bot.user}")
    await kexobot.initialize()
    main_loop_task.start()
    hourly_loop_task.start()
    while not kexobot.lavalink_servers:
        await asyncio.sleep(1)
    await kexobot.connect_node()


@bot.event
async def on_command_error(ctx: discord.ApplicationContext, error) -> None:
    if isinstance(error, commands.errors.CommandNotFound):
        embed = discord.Embed(
            title="",
            description=f"🚫 This command doesn't exist.",
            color=discord.Color.from_rgb(r=255, g=0, b=0)
        )
        embed.set_footer(text="Message will be deleted in 20 seconds.")
        await ctx.send(embed=embed, delete_after=20)


@bot.event
async def on_application_command_error(ctx: discord.ApplicationContext, error) -> None:
    if isinstance(error, commands.CommandOnCooldown):
        error_str = str(error).split()
        embed = discord.Embed(
            title="",
            description=f"🚫 You're sending too much!, try again in `{error_str[7]}`.",
            color=discord.Color.from_rgb(r=255, g=0, b=0)
        )
        embed.set_footer(text="Message will be deleted in 20 seconds.")
        return await ctx.respond(embed=embed, ephemeral=True, delete_after=20)
    raise error


bot.run(DISCORD_TOKEN)
