import random
from datetime import datetime, timedelta
from typing import Literal

import asyncpraw.reddit
import asyncpraw.models
import discord
import httpx
import imgflip
import requests

from discord.ext import commands
from discord.commands import slash_command
from discord import option

from asyncprawcore.exceptions import (
    AsyncPrawcoreException,
    ResponseException,
    RequestException,
)
from app.constants import (
    ROAST_COMMANDS_MSG,
    IMGFLIP_PASSWORD,
    IMGFLIP_USERNAME,
    SHITPOST_SUBREDDITS_DEFAULT,
    REDDIT_VIDEO_STRIP,
    KYS_MESSAGES,
    DB_CACHE,
    KEXO_SERVER,
    SISKA_GANG_SERVER,
)
from app.utils import (
    load_text_file,
    download_video,
    generate_user_data,
    generate_temp_user_data,
)


class FunStuff(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.bot_config = self.bot.bot_config
        self.user_data = self.bot.user_data
        self.user_data_loaded = self.bot.user_data_loaded
        self.temp_user_data = self.bot.temp_user_data
        self.reddit_agent = self.bot.reddit_agent
        self.session: httpx.AsyncClient = self.bot.session

        self.topstropscreenshot = load_text_file("topstropscreenshot")
        self.kotrmelce = load_text_file("kotrmelec")
        self.imgflip_client = imgflip.Imgflip(
            username=IMGFLIP_USERNAME,
            password=IMGFLIP_PASSWORD,
            session=requests.Session(),
        )
        self.idk_count = 0

    @slash_command(
        name="kotrmelec",
        description="Legendárne školské kotrmelce",
        guild_ids=[KEXO_SERVER, SISKA_GANG_SERVER],
    )
    async def kotrmelec(self, ctx: discord.ApplicationContext) -> None:
        await ctx.respond(random.choice(self.kotrmelce))

    @slash_command(
        name="topstropscreenshot",
        description="Topové fotečky z online hodín",
        guild_ids=[KEXO_SERVER, SISKA_GANG_SERVER],
    )
    async def top_strop_screenshot(self, ctx: discord.ApplicationContext) -> None:
        await ctx.respond(random.choice(self.topstropscreenshot))

    @slash_command(
        name="roast",
        description="Lamar roast",
        guild_ids=[KEXO_SERVER, SISKA_GANG_SERVER],
    )
    async def roast(self, ctx: discord.ApplicationContext) -> None:
        await ctx.respond(ROAST_COMMANDS_MSG)

    @slash_command(name="spam", description="Spams words, max is 50.  (Admin)")
    @discord.default_permissions(administrator=True)
    @commands.cooldown(1, 50, commands.BucketType.user)
    @option("integer", description="Max is 50.", min_value=1, max_value=50)
    async def spam(
        self, ctx: discord.ApplicationContext, word: str, integer: int
    ) -> None:
        await ctx.respond(word)
        for _ in range(integer - 1):
            await ctx.send(word)

    @slash_command(
        name="kys",
        description="Keď niekoho nemáš rád.",
        guild_ids=[KEXO_SERVER, SISKA_GANG_SERVER],
    )
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def kys(
        self, ctx: discord.ApplicationContext, member: discord.Member
    ) -> None:
        meme_img = await self.generate_meme(ctx, member)

        await ctx.respond(f"**{random.choice(KYS_MESSAGES)}** {member.mention}")

        for _ in range(19):
            await ctx.send(f"**{random.choice(KYS_MESSAGES)}** {member.mention}")
        await ctx.send(meme_img)

    @slash_command(
        name="idk", description="Idk.", guild_ids=[KEXO_SERVER, SISKA_GANG_SERVER]
    )
    async def idk(self, ctx: discord.ApplicationContext) -> None:
        self.idk_count += 1
        if self.idk_count < 5:
            await ctx.respond("idk")
            return
        await ctx.respond(
            "https://media.discordapp.net/attachments"
            "/796453724713123870/1042486203842306159/image.png"
        )
        self.idk_count = 0

    @slash_command(
        name="shitpost", description="Random post from various shitposting subreddits."
    )
    @option("nsfw", bool, description="Turn on/off NSFW posts.", required=False)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def shitpost(self, ctx: discord.ApplicationContext) -> None:
        await self.process_shitpost(ctx)

    async def process_shitpost(self, ctx: discord.ApplicationContext) -> None:
        user_id = ctx.author.id
        user_data, temp_user_data = await self._load_user_data(ctx)

        multireddit: asyncpraw.models.Multireddit = temp_user_data["multireddit"]
        limit = temp_user_data["search_limit"] + 1

        try:
            async for submission in multireddit.hot(limit=limit):
                # If post is locked, or is stickied, or it's a poll, skip it
                is_valid = await self._is_valid_submission(
                    submission, user_data, temp_user_data
                )
                if not is_valid:
                    continue

                embed = await self.create_reddit_embed(submission)

                if submission.media:
                    await ctx.respond(embed=embed)
                    await self.post_video(ctx, submission.permalink)
                # If it has multiple images
                elif hasattr(submission, "gallery_data"):
                    await ctx.respond(embed=embed)
                    await self.send_multiple_images(ctx, submission)
                else:
                    embed.set_image(url=submission.url)
                    await ctx.respond(embed=embed)

                self._update_temp_user_data(user_id, submission.permalink)
                break

        except (AsyncPrawcoreException, RequestException, ResponseException):
            await self.reddit_unresponsive_msg(ctx)

    def _update_temp_user_data(self, user_id: int, submission_url: str) -> None:
        self.temp_user_data[user_id]["viewed_posts"].add(submission_url)
        self.temp_user_data[user_id]["search_limit"] += 1

    @staticmethod
    async def _is_valid_submission(
        submission: asyncpraw.models.Submission,
        user_data: dict,
        temp_user_data: dict,
    ) -> bool:
        if submission.locked or submission.stickied or hasattr(submission, "poll_data"):
            return False

        if submission.permalink in temp_user_data["viewed_posts"]:
            return False

        nsfw_posts: bool = user_data["nsfw_posts"]
        if submission.over_18 and not nsfw_posts:
            return False

        return True

    async def _load_user_data(self, ctx: discord.ApplicationContext) -> tuple:
        user_id = ctx.author.id
        user_data = self.user_data_loaded.get(user_id)
        if user_data:
            return user_data["reddit"], self.temp_user_data[user_id]

        await ctx.defer()

        user_data = await self.user_data.find_one({"_id": user_id})  # Load from DB
        if user_data:  # If not in DB, create new user data
            user_data = user_data["reddit"]
            self.user_data_loaded[user_id] = {"reddit": user_data}

            temp_user_data = await generate_temp_user_data(
                self.reddit_agent, user_data["subreddits"], user_id
            )
        else:
            user_data = generate_user_data()  # Create new user data
            print(
                "Creating new user data for user:", await self.bot.fetch_user(user_id)
            )

            await self.user_data.insert_one({"_id": user_id, "reddit": user_data})
            self.user_data_loaded[user_id] = {"reddit": user_data}
            temp_user_data = await generate_temp_user_data(
                self.reddit_agent, SHITPOST_SUBREDDITS_DEFAULT, user_id
            )

        self.user_data_loaded[user_id]["reddit"] = user_data
        self.temp_user_data[user_id] = temp_user_data
        return user_data, temp_user_data

    async def generate_meme(
        self, ctx: discord.ApplicationContext, member: discord.Member
    ) -> str:
        text = random.choice(
            (
                f"72598094; ;{member.name};50",
                f"91545132;tento typek je cisty retard;{member.name};50",
                f"368961738;{ctx.author.name};{member.name};50",
                f"369517762;{member.name}; ;65",
                f"153452716;{member.name}; ;50",
            )
        ).split(";")

        return self.imgflip_client.make_meme(
            template=text[0],
            top_text=text[1],
            bottom_text=text[2],
            max_font_size=text[3],
        )

    @staticmethod
    async def send_multiple_images(
        ctx: discord.ApplicationContext, submission: asyncpraw.reddit.Submission
    ) -> None:
        for images in submission.gallery_data["items"]:
            await ctx.send(f"https://i.redd.it/{images['media_id']}.jpg")

    @staticmethod
    async def post_video(ctx: discord.ApplicationContext, submission_url: str) -> None:
        video_url = submission_url.split("/")[4]
        await ctx.send(f"https://rxddit.com/{video_url}/", suppress=False)

    async def create_reddit_embed(
        self, submission: asyncpraw.reddit.Submission
    ) -> discord.Embed:
        subreddit: asyncpraw.models.Subreddit = submission.subreddit

        embed = discord.Embed(
            title=f"{submission.title}",
            url=f"https://www.reddit.com{submission.permalink}",
            color=discord.Color.from_rgb(255, 69, 0),
        )
        embed.set_footer(
            text=f"r/{subreddit.display_name} ｜🔺{submission.score}｜💬 {submission.num_comments}",
            icon_url=self.bot.subreddit_icons[subreddit.display_name],
        )
        embed.timestamp = datetime.fromtimestamp(submission.created_utc)
        return embed

    @staticmethod
    async def reddit_unresponsive_msg(ctx: discord.ApplicationContext) -> None:
        embed = discord.Embed(
            title="",
            description="🚫 Reddit didn't respond, try again in a minute.\nWhat could cause "
            "error? - Reddit is down, Subreddit is locked, API might be overloaded",
            color=discord.Color.from_rgb(r=255, g=0, b=0),
        )
        embed.set_footer(text="Message will be deleted in 20 seconds.")
        await ctx.respond(embed=embed, ephemeral=True, delete_after=20)


def setup(bot: commands.Bot):
    bot.add_cog(FunStuff(bot))
