import discord
import random
import imgflip
import requests

from datetime import datetime, timedelta
from discord.ext import commands
from discord.commands import slash_command
from discord import option
from bson.objectid import ObjectId
from asyncprawcore.exceptions import AsyncPrawcoreException, ResponseException, RequestException
from constants import (ROAST_COMMANDS_MSG, IMGFLIP_PASSWORD, IMGFLIP_USERNAME, SHITPOST_SUBREDDITS, REDDIT_VIDEO_STRIP,
                       KYS_MESSAGES)
from utils import load_text_file, VideoDownloader


class FunStuff(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.school_images = bot.database.find_one({'_id': ObjectId('618945c8221f18d804636965')})['topstrop'].split(
            '\n')
        self.kotrmelce = load_text_file("kotrmelec")
        self.imgflip_client = imgflip.Imgflip(username=IMGFLIP_USERNAME, password=IMGFLIP_PASSWORD,
                                              session=requests.Session())
        self.idk_count = 0

    @slash_command(name="kotrmelec", description="Legendárne školské kotrmelce",
                   guild_ids=[692810367851692032, 765262686908186654])
    async def kotrmelec(self, ctx) -> None:
        await ctx.respond(random.choice(self.kotrmelce))

    @slash_command(name="topstropscreenshot", description="Topové fotečky z online hodín",
                   guild_ids=[692810367851692032, 765262686908186654])
    async def top_strop_screenshot(self, ctx) -> None:
        await ctx.respond(random.choice(self.school_images))

    @slash_command(name="roast", description="Lamar roast", guild_ids=[692810367851692032, 765262686908186654])
    async def roast(self, ctx) -> None:
        await ctx.respond(ROAST_COMMANDS_MSG)

    @slash_command(name='spam', description='Spams words, max is 50.  (Admin)')
    @discord.default_permissions(administrator=True)
    @commands.cooldown(1, 50, commands.BucketType.user)
    @option(
        'integer',
        description='Max is 50.',
        min_value=1,
        max_value=50
    )
    async def spam(self, ctx, word: str, integer: int) -> None:
        await ctx.respond(word)
        for _ in range(integer - 1):
            await ctx.send(word)

    @slash_command(name='kys', description='Keď niekoho nemáš rád.',
                   guild_ids=[692810367851692032, 765262686908186654])
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def kys(self, ctx, member: discord.Member) -> None:
        meme_img = await self.generate_meme(ctx, member)

        await ctx.respond(
            f"**{random.choice(KYS_MESSAGES)}** {member.mention}")

        for _ in range(19):
            await ctx.send(
                f"**{random.choice(KYS_MESSAGES)}** {member.mention}")
        await ctx.send(meme_img)

    @slash_command(name='idk', description='Idk.',
                   guild_ids=[692810367851692032, 765262686908186654])
    async def idk(self, ctx) -> None:
        self.idk_count += 1
        if self.idk_count < 5:
            return await ctx.respond("idk")
        await ctx.respond('https://media.discordapp.net/attachments/796453724713123870/1042486203842306159/image.png')
        self.idk_count = 0

    async def process_shitpost(self, ctx) -> None:
        guild_id = str(ctx.guild.id) if ctx.guild else str(ctx.user.id)

        if guild_id not in self.bot.subbredit_cache:
            await self.create_guild_dataset(guild_id)

        guild_subreddit_cache = self.bot.subbredit_cache[guild_id]
        subreddit = await self.bot.reddit.subreddit(SHITPOST_SUBREDDITS[guild_subreddit_cache.get("which_subreddit")])
        await self.up_search_level(guild_subreddit_cache)

        try:
            pos = 0
            async for submission in subreddit.hot(
                    limit=guild_subreddit_cache.get('search_level') + 3):
                pos += 1
                # Limiting how much to serach
                if pos < guild_subreddit_cache.get('search_level'):
                    continue
                # If pinned, or is a thread
                if submission.is_self or submission.stickied:
                    continue
                # If already sent
                if submission.url in guild_subreddit_cache.get('links'):
                    continue
                # If it's nsfw and setting wasn't set to nsfw
                if submission.over_18 and not guild_subreddit_cache.get('links'):
                    continue

                embed = await self.create_reddit_embed(submission,
                                                       SHITPOST_SUBREDDITS[
                                                           guild_subreddit_cache.get('which_subreddit')])

                if submission.media:
                    await ctx.respond(embed=embed)
                    await self.upload_video(ctx, submission)
                # If it has multiple images
                elif hasattr(submission, 'gallery_data'):
                    await ctx.respond(embed=embed)
                    await self.send_multiple_images(ctx, submission)
                else:
                    embed.set_image(url=submission.url)
                    await ctx.respond(embed=embed)

                await self.cache_viewed_link(submission.url, guild_id)
                break

        except (AsyncPrawcoreException, RequestException, ResponseException):
            await self.reddit_unresponsive_msg(ctx)

    @slash_command(name='shitpost', description='Random post from various shitposting subreddits.',
                   guild_ids=[692810367851692032])
    @option("nsfw", bool, description='Turn on/off NSFW posts.', required=False)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def shitpost(self, ctx, nsfw: False) -> None:
        if nsfw:
            if ctx.guild:
                self.bot.subbredit_cache[str(ctx.guild.id)]['nsfw'] = nsfw
            else:  # If DM
                self.bot.subbredit_cache[str(ctx.user.id)]['nsfw'] = nsfw
            await ctx.respond(f'NSFW Tags were set to `{nsfw}`.')
        await self.process_shitpost(ctx)

    async def cache_viewed_link(self, submission_url, guild_id) -> None:
        self.bot.subbredit_cache[guild_id]['links'] += (f'{submission_url}*'
                                                        f'{(datetime.now()
                                                            + timedelta(hours=20)).strftime("%I").lstrip("0")}\n')

    async def generate_meme(self, ctx, member: discord.Member) -> str:
        text = random.choice((f'72598094; ;{member.name};50',
                              f'91545132;tento typek je cisty retard;{member.name};50',
                              f'368961738;{ctx.author.name};{member.name};50',
                              f'369517762;{member.name}; ;65',
                              f'153452716;{member.name}; ;50')).split(';')

        return self.imgflip_client.make_meme(
            template=text[0],
            top_text=text[1],
            bottom_text=text[2],
            max_font_size=text[3])

    @staticmethod
    async def up_search_level(guild_subreddit_cache) -> None:
        guild_subreddit_cache['which_subreddit'] = (guild_subreddit_cache['which_subreddit'] - 1) % len(
            SHITPOST_SUBREDDITS)
        # If it's the last subreddit, search more
        if guild_subreddit_cache['which_subreddit'] == len(SHITPOST_SUBREDDITS) + 1:
            guild_subreddit_cache['search_level'] += 1

    @staticmethod
    async def send_multiple_images(ctx, submission) -> None:
        for images in submission.gallery_data['items']:
            await ctx.send(f'https://i.redd.it/{images["media_id"]}.jpg')

    @staticmethod
    async def upload_video(ctx, submission) -> None:
        msg = await ctx.send('Downloading video, please wait...')
        url = submission.media.get('reddit_video')['fallback_url']

        for replacement in REDDIT_VIDEO_STRIP:
            url = url.replace(replacement, 'DASH_220')

        audio_url = url.replace('DASH_220.mp4?source=fallback', 'DASH_AUDIO_128.mp4')
        url = (f"https://sd.rapidsave.com/download.php?permalink=https://reddit.com"
               f"{submission.permalink}&video_url={url}&audio_url={audio_url}")

        video = await videoDownloader.download_video(url, submission.over_18)
        await msg.edit(content=None, file=video)

    @staticmethod
    async def create_reddit_embed(submission: object, subbreddit_name: str) -> discord.Embed:
        embed = discord.Embed(title=f'{submission.title}', url=f'https://www.reddit.com{submission.permalink}',
                              color=discord.Color.orange())
        embed.set_footer(text=f'r/{subbreddit_name} ｜🔺{submission.score}｜💬 {submission.num_comments}',
                         icon_url='https://media.discordapp.net/attachments/796453724713123870'
                                  '/1293985674696855552/reddit-logo-2436.png?ex=67095d91&is=67080c11&hm'
                                  '=9728ebfb9f2b540d6dcac25149e9d620b249ef724f4b004cf831b9b6c5868083&=&format'
                                  '=webp&quality=lossless')
        embed.timestamp = datetime.fromtimestamp(submission.created_utc)
        return embed

    async def create_guild_dataset(self, guild_id) -> None:
        self.bot.database.update_one({'_id': ObjectId('61795a8950149bebf7666e55')},
                                     {"$set": {guild_id: '1,False,,0'}})
        self.bot.subbredit_cache[guild_id] = {'search_level': 0, 'nsfw': False, 'links': '', 'which_subreddit': 0}

    @staticmethod
    async def reddit_unresponsive_msg(ctx) -> None:
        embed = discord.Embed(title="",
                              description=f"🚫 Reddit didn't respond, try again in a minute.\nWhat could cause "
                                          f"error? - Reddit is down, Subreddit is locked, API might be overloaded",
                              color=discord.Color.from_rgb(r=255, g=0, b=0))
        embed.set_footer(text='Message will be deleted in 20 seconds.')
        await ctx.respond(embed=embed, ephemeral=True, delete_after=20)


videoDownloader = VideoDownloader()


def setup(bot: commands.Bot):
    bot.add_cog(FunStuff(bot))
