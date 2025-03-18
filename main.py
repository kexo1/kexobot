import discord
import asyncpraw
import httpx
import dns.resolver
import random
import asyncpraw
import discord
import wavelink

from fake_useragent import UserAgent
from discord.ext import tasks, commands
from pymongo import MongoClient
from datetime import datetime
from bson import ObjectId

from constants import DISCORD_TOKEN, MONGO_DB_URL, REDDIT_PASSWORD, REDDIT_SECRET, REDDIT_USER_AGENT, REDDIT_USERNAME, \
    REDDIT_CLIENT_ID, HUMOR_SECRET, CLEAR_CACHE_HOUR
from utils import return_dict

from classes.Esutaze import Esutaze
from classes.OnlineFix import OnlineFix
from classes.Game3rb import Game3rb
from classes.ElektrinaVypadky import ElektrinaVypadky
from classes.RedditCrackwatch import RedditCrackwatch
from classes.RedditFreegamefindings import RedditFreegamefindings

dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ['8.8.8.8']

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='+', case_insensitive=True, intents=intents)


# TODO: Reorganize MongoDB database
# TODO: MongoDB constants instead of hardcoded values
# TODO: Make classes in /classes/ more modular
# TODO: Auto fetch lavalink server at startup

class KexoBOT:
    def __init__(self) -> None:
        self.user_kexo = None
        self.session = None
        self.database = MongoClient(MONGO_DB_URL)["KexoBOTDatabase"]["KexoBOTCollection"]

        self.reddit = asyncpraw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_SECRET,
            user_agent=REDDIT_USER_AGENT,
            username=REDDIT_USERNAME,
            password=REDDIT_PASSWORD,
        )
        # Attach to bot, so we can use it in cogs
        bot.database = self.database
        bot.reddit = self.reddit
        bot.subbredit_cache = return_dict(
            self.database.find_one({'_id': ObjectId('61795a8950149bebf7666e55')}, {'_id': False}))

        self.onlinefix = None
        self.game3rb = None
        self.reddit_freegamefindings = None
        self.reddit_crackwatch = None
        self.elektrina_vypadky = None
        self.esutaze = None
        self.main_loop_counter = 0

    async def initialize(self, bot):
        await self.fetch_users()
        await self.create_session()

        self.onlinefix = OnlineFix(self.session, self.database, bot)
        self.game3rb = Game3rb(self.session, self.database, bot)
        self.reddit_freegamefindings = RedditFreegamefindings(self.database, self.reddit)
        self.reddit_crackwatch = RedditCrackwatch(self.database, self.reddit, bot)
        self.elektrina_vypadky = ElektrinaVypadky(self.session, self.database, self.user_kexo)
        self.esutaze = Esutaze(self.session, self.database, bot)

    async def create_session(self):
        self.session = httpx.AsyncClient()
        self.session.verify = True
        self.session.headers = {'User-Agent': UserAgent().random}
        print('Httpx session initialized.')

    @staticmethod
    async def connect_node() -> None:
        nodes = [
            wavelink.Node(uri='http://sk.kexoservers.online:2333', password="kexopexo", retries=2, resume_timeout=0)]

        await wavelink.Pool.connect(nodes=nodes, client=bot)
        bot.node = nodes

    async def set_joke(self):
        # insults, dark
        joke_categroy = random.choice(('jewish', 'racist'))
        joke = await self.session.get(
            f"https://api.humorapi.com/jokes/random?max-length=128&include-tags="
            f"{joke_categroy}&api-key={HUMOR_SECRET}").json().get('joke')
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=joke))

    async def fetch_users(self):
        self.user_kexo = await bot.fetch_user(402221830930432000)
        print(f'User {self.user_kexo.name} fetched.')

    async def update_reddit_cache(self, now):
        update = {}
        for guild_id, cache in bot.subbredit_cache.items():
            # If midnight, set search_level to 0
            to_upload = ['0' if now.hour == CLEAR_CACHE_HOUR else str(cache['search_level']),
                         str(cache.get('nsfw')),
                         cache.get('links'),
                         str(cache.get('which_subreddit'))]
            # Remove links at midnight
            reddit_links = [reddit_link for reddit_link in to_upload[2].split('\n') if
                            not reddit_link or reddit_link.split('*')[1] != str(now.hour)]
            to_upload[2] = '\n'.join(reddit_links)
            update[guild_id] = ','.join(to_upload)

        self.database.update_many({'_id': ObjectId('61795a8950149bebf7666e55')}, {"$set": update})
        bot.subbredit_cache = return_dict(update)

    async def main_loop(self):
        if self.main_loop_counter == 0:
            self.main_loop_counter = 1
            await self.reddit_freegamefindings.run()

        elif self.main_loop_counter == 1:
            self.main_loop_counter = 2
            await self.game3rb.run()

        elif self.main_loop_counter == 2:
            self.main_loop_counter = 3
            await self.onlinefix.run()

        elif self.main_loop_counter == 3:
            self.main_loop_counter = 4
            await self.reddit_crackwatch.run()

        elif self.main_loop_counter == 4:
            self.main_loop_counter = 0
            await self.esutaze.run()

    async def hourly_loop(self):
        now = datetime.now()

        if now.hour == 0:
            await self.set_joke()

        await self.update_reddit_cache(now)
        await self.elektrina_vypadky.run()


kexobot = KexoBOT()


def create_cog_session():
    bot.session = httpx.AsyncClient()
    bot.session.verify = True
    bot.session.headers = {'User-Agent': UserAgent().random}


def setup_cogs():
    create_cog_session()
    bot.load_extension("cogs.Play")
    bot.load_extension("cogs.Listeners")
    bot.load_extension("cogs.Queue")
    bot.load_extension("cogs.Audio")
    bot.load_extension("cogs.Disconnect")
    bot.load_extension("cogs.FunStuff")
    bot.load_extension("cogs.Commands")
    bot.load_extension("cogs.DatabaseManager")
    print('Cogs loaded.')


setup_cogs()


@tasks.loop(minutes=5)
async def main_loop_task():
    await kexobot.main_loop()


@tasks.loop(hours=1)
async def hourly_loop_task():
    await kexobot.hourly_loop()


@main_loop_task.before_loop
async def before_main_loop():
    await bot.wait_until_ready()


@hourly_loop_task.before_loop
async def before_hourly_loop():
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await kexobot.initialize(bot)
    main_loop_task.start()
    hourly_loop_task.start()
    await kexobot.connect_node()


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.errors.CommandNotFound):
        embed = discord.Embed(title="",
                              description=f"🚫 This command doesn't exist.",
                              color=discord.Color.from_rgb(r=255, g=0, b=0))
        embed.set_footer(text='Message will be deleted in 20 seconds.')
        await ctx.send(embed=embed, delete_after=20)


@bot.event
async def on_application_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        error_str = str(error).split()
        embed = discord.Embed(title="",
                              description=f"🚫 You're sending too much!, try again in `{error_str[7]}`.",
                              color=discord.Color.from_rgb(r=255, g=0, b=0))
        embed.set_footer(text='Message will be deleted in 20 seconds.')
        return await ctx.respond(embed=embed, ephemeral=True, delete_after=20)
    raise error


bot.run(DISCORD_TOKEN)
