import socket
from datetime import datetime, timedelta
import os
import random
import time
from fake_useragent import UserAgent

import discord
import imgflip
import requests
import aiohttp
import asyncio

from bs4 import BeautifulSoup
from pymongo import MongoClient
from bson.objectid import ObjectId
from discord import option
from discord.ext import commands, tasks
from discord.ui import Button, View
import asyncpraw
import asyncprawcore.exceptions
import wavelink

intents = discord.Intents.default()
ua = UserAgent()

# noinspection PyUnresolvedReferences
intents.auto_moderation_configuration = False
intents.auto_moderation_execution = False
intents.message_content = True
intents.reactions = False
intents.bans = False
intents.dm_reactions = False
intents.emojis = False
intents.emojis_and_stickers = False
intents.invites = False
intents.scheduled_events = False
intents.webhooks = False


class Bot(commands.Bot):
    def __init__(self, *, intents: discord.Intents):
        # Set intents and command prefix
        super().__init__(
            intents=intents,
            command_prefix='+',
            case_insensitive=True
        )

    async def on_ready(self):
        await bot.setup_bot()
        print(f'Logged in {self.user}')

    # noinspection PyAttributeOutsideInit
    async def setup_bot(self):
        # http://192.168.1.3:2333
        # http://kexo.duckdns.org:2333
        nodes = [wavelink.Node(uri='http://192.168.1.3:2333', password="kexopexo", retries=2, resume_timeout=0)]

        await wavelink.Pool.connect(nodes=nodes, client=self)

        self.database = MongoClient(
            f"mongodb+srv://{os.getenv('MONGO_URL')}@cluster0.exygx.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")[
            "KexoBOTDatabase"]["KexoBOTCollection"]

        self.main_class = MainBOT()
        self.node = nodes


bot = Bot(intents=intents)
bot.remove_command("help")

activity = ('Valheim', 'Counter-Strike: Global Offensive', 'Minecraft', 'Doom Eternal', 'Red Dead Redemption 2',
            'Cyberbug 2077', 'Python', 'Gears of War 5',
            'Call of Duty Warzone 2.0', 'Forza Horizon 4', 'Forza Horizon 5', 'Superfighters Deluxe',
            '7 Days to Die', 'BeamNG.drive', "Tom Clancy's The Division 2", 'Valorant', 'Fallout 4', 'Battlefield V',
            'God of War', 'Halo: Masterchief Collection', 'Far Cry 6')


def setup():
    bot.load_extension("cogs.play")
    bot.load_extension("cogs.listeners")
    bot.load_extension("cogs.queue")
    bot.load_extension("cogs.audio")
    bot.load_extension("cogs.disconnect")


setup()


class MainBOT:
    def __init__(self):
        self.imgflip_client = imgflip.Imgflip(username="Kexotv", password=os.getenv('IMGFLIP_PASSWORD'),
                                              session=requests.Session())

        self.obrazok = bot.database.find_one({'_id': ObjectId('618945c8221f18d804636965')})
        self.obrazok = self.obrazok['topstrop'].split('\n')

        self.reddit = asyncpraw.Reddit(
            client_id="4JQ0g3ez1zP5zjhWvE-gNg",
            client_secret=os.getenv('REDDIT_SECRET'),
            user_agent="KexoXD",
            username="Kexotv",
            password=os.getenv('REDDIT'),
        )

        self.session = requests.Session()
        self.session.verify = True
        self.session.headers = {
            'User-Agent': ua.random
        }

        self.subreddits = (
            'shid_and_camed', 'discordVideos', 'shitposting', 'ppnojutsu', 'okbuddyretard', 'MoldyMemes', 'MemeVideos',
            'hmm', 'doodoofard', 'dankvideos', '19684', 'whenthe')

        self.subbredit_cache = bot.database.find_one({'_id': ObjectId('61795a8950149bebf7666e55')}, {'_id': False})
        self.subbredit_cache = return_dict(self.subbredit_cache)

    async def imflip_api(self, ctx, member):
        text = random.choice(
            (f'72598094; ;{member.name};50',
             f'91545132;tento typek je cisty retard;{member.name};50',
             f'368961738;{ctx.author.name};{member.name};50',
             f'369517762;{member.name}; ;65',
             f'153452716;{member.name}; ;50')).split(';')

        meme = self.imgflip_client.make_meme(
            template=text[0],
            top_text=text[1],
            bottom_text=text[2],
            max_font_size=text[3])

        # Respond to see who sent command
        await ctx.respond(
            f"**{random.choice(('Kys', 'Skap', 'Zdechni', 'Zahraj sa na luster', 'Choď pobozkať kolajnice keď príde vlak', 'Zec mi kar'))}** {member.mention}")

        for _ in range(19):
            await ctx.send(
                f"**{random.choice(('Kys', 'Skap', 'Zdechni', 'Zahraj sa na luster', 'Choď pobozkať kolajnice keď príde vlak', 'Zec mi kar'))}** {member.mention}")
        await ctx.send(meme)

    async def shitpost(self, ctx):
        guild_id = str(ctx.guild.id) if ctx.guild else str(ctx.user.id)

        if guild_id not in self.subbredit_cache:
            bot.database.update_one({'_id': ObjectId('61795a8950149bebf7666e55')},
                                    {"$set": {guild_id: '1,False,,-1'}})
            self.subbredit_cache[guild_id] = {'search_level': 0, 'nsfw': False, 'links': '', 'which_subreddit': -1}

        guild_subreddit_cache = self.subbredit_cache[guild_id]
        subbreddit_name = self.subreddits[guild_subreddit_cache["which_subreddit"]]

        subreddit = await self.reddit.subreddit(subbreddit_name)

        guild_subreddit_cache['which_subreddit'] = (guild_subreddit_cache['which_subreddit'] + 1) % 12
        if guild_subreddit_cache['which_subreddit'] == 11: guild_subreddit_cache['search_level'] += 1

        pos = 0
        try:
            async for submission in subreddit.hot(
                    limit=guild_subreddit_cache['search_level'] + 3):
                pos += 1
                if pos < guild_subreddit_cache['search_level']:
                    continue

                if submission.is_self or submission.stickied or submission.url in guild_subreddit_cache['links']:
                    continue

                if submission.over_18 and not guild_subreddit_cache['nsfw']:
                    continue

                embed = discord.Embed(title=f'{submission.title}', url=f'https://www.reddit.com{submission.permalink}',
                                      color=discord.Color.orange())
                embed.set_footer(text=f'r/{subbreddit_name} ｜🔺{submission.score}｜💬 {submission.num_comments}',
                                 icon_url='https://www.vectorico.com/wp-content/uploads/2018/08/Reddit-logo.png')
                embed.timestamp = datetime.fromtimestamp(submission.created_utc)

                if submission.media:
                    await ctx.respond(embed=embed)
                    msg = await ctx.send('Downloading video, please wait...')
                    url = submission.media['reddit_video']['fallback_url']

                    to_replace = ('DASH_360', 'DASH_480', 'DASH_720', 'DASH_1080')
                    for replacement in to_replace:
                        url = url.replace(replacement, 'DASH_220')

                    audio_url = url.replace('DASH_220.mp4?source=fallback', 'DASH_AUDIO_128.mp4')
                    url = f"https://sd.rapidsave.com/download.php?permalink=https://reddit.com{submission.permalink}&video_url={url}&audio_url={audio_url}"

                    file_video = await videodownloader.download_video(url, submission.over_18, submission.media)
                    await msg.edit(content=None, file=file_video)

                # If it has multiple images
                elif hasattr(submission, 'gallery_data'):
                    await ctx.respond(embed=embed)
                    for images in submission.gallery_data['items']:
                        await ctx.send(f'https://i.redd.it/{images["media_id"]}.jpg')
                else:
                    embed.set_image(url=submission.url)
                    await ctx.respond(embed=embed)

                self.subbredit_cache[guild_id][
                    'links'] += f'{submission.url}*{(datetime.now() + timedelta(hours=20)).strftime("%I").lstrip("0")}\n'
                break

        except (
                asyncprawcore.exceptions.AsyncPrawcoreException, asyncprawcore.exceptions.RequestException,
                asyncprawcore.exceptions.ResponseException, AssertionError):
            embed = discord.Embed(title="",
                                  description=f"🚫 Reddit didn't respond, try again in a minute.\nWhat could cause error? - Reddit is down, Subreddit is locked, API might be overloaded",
                                  color=discord.Color.from_rgb(r=255, g=0, b=0))
            embed.set_footer(text='Message will be deleted in 20 seconds.')
            await ctx.respond(embed=embed, ephemeral=True, delete_after=20)

    @staticmethod
    async def manage_list(collection, manage):

        if manage is False:
            listing = bot.database.find_one({'_id': ObjectId('6178211ec5f5c08c699b8fd3')})

        if collection == 'Games':
            if manage is False:
                listing = listing['games']
            else:
                bot.database.update_one({'_id': ObjectId('6178211ec5f5c08c699b8fd3')},
                                        {'$set': {'games': manage}})
        elif collection == 'Site exceptions':
            if manage is False:
                listing = listing['freegame_exceptions']
            else:
                bot.database.update_one({'_id': ObjectId('6178211ec5f5c08c699b8fd3')},
                                        {'$set': {'freegame_exceptions': manage}})
        elif collection == 'Crackwatch exceptions':
            if manage is False:
                listing = listing['crackwatch_exceptions']
            else:
                bot.database.update_one({'_id': ObjectId('6178211ec5f5c08c699b8fd3')},
                                        {'$set': {'crackwatch_exceptions': manage}})
        elif collection == 'Esutaze exceptions':
            if manage is False:
                listing = listing['esutaze_exceptions']
            else:
                bot.database.update_one({'_id': ObjectId('6178211ec5f5c08c699b8fd3')},
                                        {'$set': {'esutaze_exceptions': manage}})

        if manage is False:
            return listing


def return_dict(subbredit_cache):
    for key in subbredit_cache:
        search_level, nsfw, links, which_subreddit = subbredit_cache[key].split(',')
        subbredit_cache[key] = {'search_level': int(search_level), 'nsfw': bool(nsfw), 'links': links,
                                'which_subreddit': int(which_subreddit)}
    return subbredit_cache


class VideoDownloader:
    def __init__(self):
        self.session = None

    async def download_video(self, url, nsfw, red):
        if not self.session:
            self.session = aiohttp.ClientSession()

        async with self.session.get(url) as response:
            with open('video.mp4', 'wb') as f:
                looped = 0
                while True:
                    chunk = await response.content.read(1024)
                    if not chunk:
                        if looped == 0:
                            print(url)
                            print(red)
                        break
                    f.write(chunk)
                    looped += 1
            if nsfw is True:
                return discord.File('video.mp4', spoiler=True)
            else:
                return discord.File('video.mp4')


async def create_session():
    return aiohttp.ClientSession()


async def main_task(main_class):
    now = datetime.now()

    if now.hour == 0:
        game = discord.Game(str(random.choice(activity)))
        await bot.change_presence(activity=discord.Game(name=game))

    # Upload to database
    update = {}
    for key, value in main_class.subbredit_cache.items():
        to_upload = ['0' if now.hour == 2 else str(value['search_level']), str(value['nsfw']), value['links'],
                     str(value['which_subreddit'])]

        reddit_links = [reddit_link for reddit_link in to_upload[2].split('\n') if
                        not reddit_link or reddit_link.split('*')[1] != str(now.hour)]
        to_upload[2] = '\n'.join(reddit_links)
        update[key] = ','.join(to_upload)

    bot.database.update_many({'_id': ObjectId('61795a8950149bebf7666e55')}, {"$set": update})
    main_class.subbredit_cache = return_dict(update)


@tasks.loop(hours=1)
async def main_loop():
    # Wait for lavalink and pymongo to connect
    while not hasattr(bot, "main_class"):
        print('Waiting for connections')
        await asyncio.sleep(3)

    await main_task(bot.main_class)


@main_loop.before_loop
async def before_my_task():
    await bot.wait_until_ready()


main_loop.start()

host_authors = []


class HostView(discord.ui.View):
    def __init__(self, author):
        super().__init__(timeout=43200, disable_on_timeout=True)
        self.author = author

    # noinspection PyUnusedLocal
    @discord.ui.button(style=discord.ButtonStyle.gray, label="I stopped hosting.", emoji='📣')
    async def button_callback(self, button, interaction):
        if interaction.user.name in host_authors:
            self.stop()

            embed = interaction.message.embeds[0]
            embed.set_author(icon_url=self.author.avatar.url,
                             name=f'{self.author.name} is no longer hosting.')
            embed.description = 'Status: **Offline**  :red_circle: '
            embed.color = discord.Color.from_rgb(r=255, g=0, b=0)

            await interaction.response.edit_message(embed=embed, view=None)
            pos = host_authors.index(self.author.name)
            host_authors.pop(pos)
        else:
            await interaction.response.send_message(
                interaction.user.mention + ', you are not author of this embed.', delete_after=5, ephemeral=True)

    async def on_timeout(self):
        self.stop()

        embed = self.message.embeds[0]
        embed.set_author(icon_url=self.author.avatar.url,
                         name=f'{self.author.name} is no longer hosting.')
        embed.description = 'Status: **Offline**  :red_circle: '
        embed.color = discord.Color.from_rgb(r=255, g=0, b=0)

        await self.message.edit(embed=embed, view=None)
        await self.author.send(
            f'You forgot to click button in {self.message.jump_url} {random.choice(("dumbass", "retard", "nitwit", "cockwomble", "dick", "prick", "cunt", "pillock", "twat", "cumdumpster"))}.')
        pos = host_authors.index(self.author.name)
        host_authors.pop(pos)


@bot.slash_command(name='host', description='Creates hosting embed, you can also choose some optional info.',
                   context={discord.InteractionContextType.guild}, guild_ids=[723197287861583885, 692810367851692032])
@option('server_name', description='Your server name.')
@option('duration', description='How long are you going to be hositng.',
        choices=['As long as I want/Before any crash.', 'Less than 15 minutes.', '15 minutes', '30 minutes',
                 '45 minutes', '1 hour', '1+ hours',
                 '2+ hours', '3+ hours'])
@option('ping', description='Should this embed ping @Deluxe or not, default is True', required=False)
@option('password', description='Server password.', required=False)
@option('region', description='Server region.', required=False)
@option('category_maps', description='What kind of server, which maps, etc...', required=False)
@option('scripts', description='Which scripts are enabled.', required=False)
@option('slots', description='How many server slots, default is 8', required=False)
@option('image', description='Add custom image url for embed, needs to end with .png, .gif and etc.', required=False)
@commands.cooldown(1, 300, commands.BucketType.user)
async def host(ctx, server_name, duration, password, region, category_maps, scripts,
        slots: int = 8, ping: bool = True, image: str = None):
    author = ctx.author

    if author not in host_authors:
        host_authors.append(author.name)

        embed = discord.Embed(
            title=server_name,
            description='Status: **Online**  :green_circle: ',
            color=discord.Color.green())

        embed.set_author(icon_url=author.avatar.url, name=f'{author.name} is now hosting!')
        embed.timestamp = datetime.utcnow()

        embed.add_field(name='Uptime:ㅤㅤ', value=duration)
        embed.set_footer(text=f'Slots: {slots}')

        if password: embed.add_field(name='Password:ㅤㅤ', value=password)
        if region: embed.add_field(name='Region:ㅤㅤ', value=region)
        if category_maps: embed.add_field(name='Category/Maps:ㅤㅤ', value=category_maps)
        if scripts: embed.add_field(name='Scripts:ㅤㅤ', value=scripts)

        if image:
            if image.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                embed.set_thumbnail(url=image)
            else:
                await ctx.respond('Image url needs to end with .jpg, .png, .gif and etc.',
                                  ephemeral=True,
                                  delete_after=10)
        if ping:
            role = discord.utils.get(ctx.guild.roles, name='Deluxe')
            await ctx.send(role.mention)

        view = HostView(author=author)
        await ctx.respond(embed=embed, view=view)
        # Timeout 15 minutes, convert to normal message
        msg = await ctx.interaction.original_response()
        msg = await ctx.channel.fetch_message(msg.id)
        view.message = msg
    else:
        return await ctx.respond(
            "You have already created host embed! Click on button embed to stop it from beign active.", delete_after=10,
            ephemeral=True)


@bot.slash_command(name='recconnect_node', description='Retry connecting to node')
@option('uri', description='Lavalink server URL (without http:// at start).')
@option('port', description='Lavalink server port.')
@option('password', description='Lavalink server password.')
async def retry_node(ctx, uri, port, password):

    embed = discord.Embed(title="",
                          description=f'**🔄 Connecting to `{uri}`**',
                          color=discord.Color.blue())
    message = await ctx.respond(embed=embed)

    nodes = [wavelink.Node(uri=f"http://{uri}:{port}", password=password, retries=1, resume_timeout=0)]
    await wavelink.Pool.connect(nodes=nodes, client=bot)
    bot.node = nodes

    await ctx.trigger_typing()
    await asyncio.sleep(2)

    try:
        await nodes[0].fetch_info()

        embed = discord.Embed(title="",
                              description=f'**✅ Connected to node `{uri}`**',
                              color=discord.Color.blue())
        await message.edit(embed=embed)

    except aiohttp.client_exceptions.ClientConnectorError:
        embed = discord.Embed(title="",
                              description=f":x: Failed to connect to `{uri}`",
                              color=discord.Color.from_rgb(r=255, g=0, b=0))
        await message.edit(embed=embed)


@bot.slash_command(name='spam', description='Spams words, max is 50.  (Admin)', context={discord.InteractionContextType.guild})
@discord.default_permissions(administrator=True)
@commands.cooldown(1, 50, commands.BucketType.user)
@option(
    'integer',
    description='Max is 50.',
    min_value=1,
    max_value=50
)
async def spam(ctx, word, integer: int):
    await ctx.respond(word)
    for _ in range(integer - 1):
        await ctx.send(word)


@bot.slash_command(name='kys', description='Keď niekoho nemáš rád.',
                   guild_ids=[692810367851692032, 765262686908186654], context={discord.InteractionContextType.guild})  # 831092366634385429
@commands.cooldown(1, 30, commands.BucketType.user)
async def kys(ctx, member: discord.Member):
    await bot.main_class.imflip_api(ctx, member)


runTime = time.time()


@bot.slash_command(name='info', description='BOT info.')
async def info(ctx):
    embed = discord.Embed(title="INFO", color=discord.Color.blue())
    embed.add_field(name="Run time:ㅤㅤ" + '\u200b',
                    value=f"{str(timedelta(seconds=round(int(time.time()) - runTime)))}")
    embed.add_field(name="Ping:ㅤㅤㅤㅤ", value=f"{round(bot.latency * 1000)} ms")
    embed.add_field(name="Version:", value="8.1.0")
    embed.add_field(name="Prefix:", value='`/` or `+`')
    embed.add_field(name="Py-cord version:ㅤ", value='2.5.0')
    embed.add_field(name="Python version:", value='3.12')
    embed.set_footer(text="Bot owner: _kexo")
    await ctx.respond(embed=embed)


@bot.slash_command(name='random_number', description='Choose number between intervals.')
async def random_number(ctx, ineteger1: int, ineteger2: int):
    if ineteger1 > ineteger2:
        ineteger2, ineteger1 = ineteger1, ineteger2
    await ctx.respond(f"I chose `{random.randint(ineteger1, ineteger2)}`")


@bot.slash_command(name='pick', description='Selects one word, words needs to be separated by space.')
@option('words', description='Seperate words by space.')
async def pick(ctx, words: str):
    words = words.split()
    await ctx.respond("I chose " + "`" + str(random.choice(words)) + "`")


@bot.slash_command(name='c', description='Clears messages, max 50 (Admin)', context={discord.InteractionContextType.guild})
@discord.default_permissions(administrator=True)
@option(
    'integer',
    description='Max is 50.',
    min_value=1,
    max_value=50
)
async def clear(ctx, integer: int):
    await ctx.channel.purge(limit=integer)
    await ctx.respond(f'`{integer}` messages cleared ✅', delete_after=20)


@bot.slash_command(guild_ids=[692810367851692032, 765262686908186654], name='z', description='Zoom kódy učitelov.')
async def zoom(ctx):
    with open('text_files/zoom.txt', encoding='utf8') as f:
        await ctx.respond(f.read())
    f.close()


@bot.slash_command(guild_ids=[692810367851692032, 765262686908186654], name='r', description='Rozvrh.')
async def rozvrh(ctx):
    channel = bot.get_channel(800627690340220968)
    messages = await channel.history(limit=1).flatten()
    for message in messages:
        try:
            return await ctx.respond(message.attachments[0].url)
        except IndexError:
            return await ctx.respond(
                'Obrázok sa nenašiel v https://discord.com/channels/765262686908186654/800627690340220968')


with open('text_files/kotrmelec.txt', encoding="utf8") as f:
    array = f.read().split('\n')


@bot.command(aliases=['k'], guild_ids=[692810367851692032, 765262686908186654])
async def kotrmelec(ctx):
    await ctx.send(random.choice(array))
    f.close()


@bot.command()
async def melisko(ctx):
    await customsong(ctx, 'https://docs.google.com/uc?export=open&id=175EgwBkb3eaqZyJ4mm8eBcaYYiB98dWk')


@bot.command()
async def traktor(ctx):
    await customsong(ctx, 'https://docs.google.com/uc?export=open&id=1x3HdcGddnwYPpKIsyyGeAef-PzuSdpKf')


@bot.command()
async def traktore(ctx):
    await customsong(ctx, 'https://docs.google.com/uc?export=open&id=180IU1YlBju6rpLJkCKS65fqKAe-rBU1n')


@bot.command()
async def kotlebovci(ctx):
    await customsong(ctx, 'https://docs.google.com/uc?export=open&id=1dB5DceiubmFKkgfPAo_n8Z7WL5rGjHZS')


@bot.command()
async def otis(ctx):
    await customsong(ctx, 'https://docs.google.com/uc?export=open&id=1bdS2JF4ss0PHi1KH-U4-yUouVqePRNxU')


@bot.command()
async def celebration(ctx):
    await customsong(ctx, 'https://docs.google.com/uc?export=open&id=15MySi_fg9to8GyAft1brTvJM1dZfNl0h')


@bot.command()
async def pisomka(ctx):
    await customsong(ctx, 'https://docs.google.com/uc?export=open&id=1JfSpQyRieBZJicfUS0biXWIuz5wZC5L4')


@bot.command()
async def coco(ctx):
    await customsong(ctx, 'https://docs.google.com/uc?export=open&id=1ygPoD4D36aXNVP9G2ZKNggBSgAfY5H73')


@bot.command()
async def atlantida(ctx):
    await customsong(ctx, 'https://docs.google.com/uc?export=open&id=1UnCtRKstg_uNJaUp7e_PNTzpuF8ulPSN')


@bot.command()
async def customsong(ctx, csong):
    voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    voice.play(discord.FFmpegPCMAudio(csong))


dumbass = ''
images_url = ('https://cdn.discordapp.com/attachments', 'https://images-ext',
              'https://media.discordapp.net/attachments/')


# noinspection PyUnboundLocalVariable
@bot.listen()
async def on_message(message):
    global dumbass

    lower_message = message.content.lower()

    if 'discord' in lower_message and 'nitro' in lower_message \
            or 'free' in lower_message and 'nitro' in lower_message \
            or 'http://' in lower_message and 'discord' in lower_message \
            or 'http://' in lower_message and 'nitro' in lower_message \
            or 'gift' in lower_message and 'discord' in lower_message:

        if dumbass != message.author:
            await message.channel.send(f'Clearing potential discord scam from {message.author.mention}.')
        dumbass = message.author
        await message.delete()


with open('text_files/vulgary.txt', encoding="utf8") as f:
    bad_words = f.read().lower()

table = str.maketrans('', '', '.,-:_§')


@bot.slash_command(name='g', description='Searches for google image.')
@option('word', description='NSFW words are not allowed.')
async def google(ctx, word):
    word = word.translate(table)

    if word.lower() in bad_words:
        return await ctx.respond(
            'https://cdn.discordapp.com/attachments/796453724713123870/886312266629267506/Bez_nazvu.png')

    soup = BeautifulSoup(requests.get('https://www.google.com/search?q={0}&tbm=isch'.format(word)).content,
                         'html.parser')
    images = soup.findAll('img')
    photo_list = []
    for image in images:
        photo = image.get('src')
        if 'gif' not in photo:
            photo_list.append(photo)
    if photo_list:
        await ctx.respond(random.choice(photo_list))
    else:
        await ctx.respond(str(ctx.author.mention) + ", no image was found")


@bot.slash_command(name='shitpost', description='Random post from various shitposting subreddits.')
@option("nsfw", bool, description='Turn on/off NSFW posts.', required=False)
@commands.cooldown(1, 5, commands.BucketType.user)
async def shitpost(ctx, nsfw):
    if nsfw is not None:
        if ctx.guild:
            bot.main_class.subbredit_cache[str(ctx.guild.id)]['nsfw'] = nsfw
        else:
            bot.main_class.subbredit_cache[str(ctx.user.id)]['nsfw'] = nsfw
        await ctx.respond(f'NSFW Tags were set to `{nsfw}`.')
    await bot.main_class.shitpost(ctx)


@bot.slash_command(name='add_to', description='Adds string to selected list.', guild_ids=[692810367851692032])
@discord.ext.commands.is_owner()
@option('collection', description='Choose database',
        choices=['Games', 'Site exceptions', 'Crackwatch exceptions', 'Esutaze exceptions'])
async def add_to(ctx, collection: str, string: str):
    listing = await bot.main_class.manage_list(collection, False)

    if string in listing:
        await ctx.respond(
            str(ctx.author.mention) + ", string `" + string + "` is already in the database, use `/show_data`")
    else:
        listing.append(string)

        await bot.main_class.manage_list(collection, listing)
        await ctx.respond(
            "String `" + string + "` was added :white_check_mark:")


@bot.slash_command(name='remove_from', description='Removes string from selected list.', guild_ids=[692810367851692032])
@discord.ext.commands.is_owner()
@option('collection', description='Choose database',
        choices=['Games', 'Site exceptions', 'Crackwatch exceptions', 'Esutaze exceptions'])
async def remove(ctx, collection: str, string: str):
    listing = await bot.main_class.manage_list(collection, False)

    if string not in listing:
        await ctx.respond(
            str(ctx.author.mention) + ", string `" + string + "` is not in the database, use `/show_data`")
    else:
        listing.pop(listing.index(string))

        await bot.main_class.manage_list(collection, listing)
        await ctx.respond(
            "String `" + string + "` was removed :white_check_mark:")


@bot.slash_command(name='show_data', description='Shows data from selected lists.', guild_ids=[692810367851692032])
@discord.ext.commands.is_owner()
@option('collection', description='Choose database',
        choices=['Games', 'Site exceptions', 'Crackwatch exceptions', 'Esutaze exceptions'])
async def show_data(ctx, collection: str):
    listing = await bot.main_class.manage_list(collection, False)

    embed = discord.Embed(title=collection, color=discord.Color.blue())
    embed.add_field(name=f'_{len(listing)} words_',
                    value='\n'.join(f'{i + 1}. {listing[i]}' for i in range(len(listing))))
    await ctx.respond(embed=embed)


count = 0


@bot.command()
async def idk(ctx):
    global count
    count += 1
    if count < 5:
        await ctx.send("idk")
    else:
        await ctx.send('https://media.discordapp.net/attachments/796453724713123870/1042486203842306159/image.png')
        count = 0


@bot.command()
async def roast(ctx):
    await ctx.send("Wassup, can a loc come up in your crib?\n"
                   "Man fuck you, I'll see you at work\n"
                   "Ah, nigga don't hate me cause I'm beautiful nigga\n"
                   "Maybe if you got rid of that yee yee ass hair cut you get some bitches on your dick.\n"
                   "Oh, better yet, Maybe Tanisha'll call your dog-ass if she ever stop fucking with that brain surgeon or lawyer she fucking with,\n"
                   "Niggaaa...\n"
                   "What?!\n"
                   "\n"
                   "https://www.youtube.com/watch?v=a5PpsUw93_E\n")


@bot.command()
async def ottesen(ctx):
    await ctx.send("Smrdí")


@bot.command(guild_ids=[692810367851692032, 765262686908186654])
async def jaked(ctx):
    await ctx.send(
        random.choice((
            'https://media.discordapp.net/attachments/796453724713123870/912369400257065052/252801592_1103020116901894_5472392002129625529_n.jpg?width=604&height=676',
            'https://cdn.discordapp.com/attachments/796453724713123870/912369400496128040/188003478_783779708956979_503787723119043525_n.jpg',
            'https://cdn.discordapp.com/attachments/796453724713123870/912369400714235944/245512660_199873272228855_8343017592804687892_n.jpg')))


@bot.command()
async def convertible(ctx):
    await ctx.send(
        'https://cdn.discordapp.com/attachments/796453724713123870/829037241829163090/DABABY_CONVERTIBLE_IN_REAL_LIFE.mp4')


@bot.command(aliases=['ss', 's'], guild_ids=[692810367851692032, 765262686908186654])
async def topstropscreenshot(ctx):
    await ctx.channel.send(random.choice(bot.main_class.obrazok))


@bot.slash_command(name='secretcommands', guild_ids=[765262686908186654],
                   description='Príkazy, ktoré sú skryté. (Admin)')
@discord.default_permissions(administrator=True)
async def secretcommands(ctx):
    with open('text_files/secret_commands.txt', encoding='utf8') as f:
        await ctx.author.send(f.read())
        await ctx.respond("Správa bola odoslaná :white_check_mark:", delete_after=10)


@bot.slash_command(name='songs', description='Príkazy na songy.',
                   guild_ids=[692810367851692032, 765262686908186654])  # 831092366634385429
async def songs(ctx):
    with open('text_files/songs.txt', encoding='utf8') as f:
        await ctx.respond(f.read())
    f.close()


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
        string = str(error).split()
        embed = discord.Embed(title="",
                              description=f"🚫 You're sending too much!, try again in `{string[7]}`.",
                              color=discord.Color.from_rgb(r=255, g=0, b=0))
        embed.set_footer(text='Message will be deleted in 20 seconds.')
        await ctx.respond(embed=embed, ephemeral=True, delete_after=20)
    else:
        raise error


videodownloader = VideoDownloader()
bot.run(os.getenv('DISCORD_TOKEN'))
