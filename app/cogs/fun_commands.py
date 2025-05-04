import random
from datetime import datetime

import asyncpraw.models
import asyncpraw.reddit
import discord
import httpx
import imgflip
import requests
from asyncprawcore.exceptions import (
    AsyncPrawcoreException,
    ResponseException,
    RequestException,
)
from discord import option
from discord.commands import slash_command
from discord.ext import commands
from discord.utils import escape_markdown
from pycord.multicog import subcommand

from app.constants import (
    ROAST_COMMANDS_MSG,
    IMGFLIP_PASSWORD,
    IMGFLIP_USERNAME,
    HUMOR_API_URL,
    JOKE_API_URL,
    DAD_JOKE_API_URL,
    JOKE_EXCLUDED_WORDS,
    KEXO_SERVER,
    SISKA_GANG_SERVER,
)
from app.response_handler import send_response
from app.utils import (
    load_text_file,
    get_user_data,
    get_guild_data,
    make_http_request,
)


class FunCommands(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.bot_config = self.bot.bot_config
        self.user_data_db = self.bot.user_data_db
        self.guild_temp_data: dict = self.bot.guild_temp_data

        self.user_data = self.bot.user_data
        self.temp_user_data = self.bot.temp_user_data
        self.reddit_agent = self.bot.reddit_agent
        self.session: httpx.AsyncClient = self.bot.session

        self.loaded_jokes: list[str] = self.bot.loaded_jokes
        self.loaded_dad_jokes: list[str] = self.bot.loaded_dad_jokes
        self.loaded_yo_mama_jokes: list[str] = self.bot.loaded_yo_mama_jokes

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

    # -------------------- Joke commands -------------------- #
    @slash_command(name="joke", description="Fetches random joke.")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def joke(self, ctx: discord.ApplicationContext) -> None:
        _, temp_guild_data = await get_guild_data(self.bot, ctx.guild_id)

        if len(temp_guild_data["jokes"]["viewed_jokes"]) % 10 == 0:
            await ctx.defer()
            jokes = await self._get_jokes()
            if not jokes:
                await send_response(ctx, "JOKE_TIMEOUT")
                return

            self.loaded_jokes.extend(jokes)
            random.shuffle(self.loaded_jokes)

        for joke in self.loaded_jokes:
            if joke in temp_guild_data["jokes"]["viewed_jokes"]:
                continue
            break

        temp_guild_data["jokes"]["viewed_jokes"].append(joke)
        self.bot.temp_guild_data[ctx.guild_id] = temp_guild_data

        joke = escape_markdown(joke)
        await ctx.respond(joke)

    @slash_command(name="dad_joke", description="Fetches random dad joke.")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def dad_joke(self, ctx: discord.ApplicationContext) -> None:
        _, temp_guild_data = await get_guild_data(self.bot, ctx.guild_id)
        if len(temp_guild_data["jokes"]["viewed_dad_jokes"]) % 10 == 0:
            await ctx.defer()
            jokes = await self._get_dadjokes()
            if not jokes:
                await send_response(ctx, "JOKE_TIMEOUT")
                return

            self.loaded_dad_jokes.extend(jokes)
            random.shuffle(self.loaded_dad_jokes)

        for joke in self.loaded_dad_jokes:
            if joke in temp_guild_data["jokes"]["viewed_dad_jokes"]:
                continue
            break

        temp_guild_data["jokes"]["viewed_dad_jokes"].append(joke)
        self.bot.temp_guild_data[ctx.guild_id] = temp_guild_data

        joke = escape_markdown(joke)
        await ctx.respond(joke)

    @slash_command(
        name="yo_mama",
        description="Yo mama joke on a discord member.",
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    @option("member", description="Discord member.")
    async def yo_mama(
        self, ctx: discord.ApplicationContext, member: discord.Member
    ) -> None:
        _, temp_guild_data = await get_guild_data(self.bot, ctx.guild_id)
        if len(temp_guild_data["jokes"]["viewed_yo_mama_jokes"]) % 10 == 0:
            await ctx.defer()
            jokes = await self._get_yo_mama_jokes()
            if not jokes:
                await send_response(ctx, "JOKE_TIMEOUT")
                return

            self.loaded_yo_mama_jokes.extend(jokes)
            random.shuffle(self.loaded_yo_mama_jokes)

        for joke in self.loaded_yo_mama_jokes:
            if joke in temp_guild_data["jokes"]["viewed_yo_mama_jokes"]:
                continue
            break

        temp_guild_data["jokes"]["viewed_yo_mama_jokes"].append(joke)
        self.bot.temp_guild_data[ctx.guild_id] = temp_guild_data

        joke = joke[0].lower() + joke[1:]
        joke = escape_markdown(joke)
        await ctx.respond(member.mention + " " + joke)

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
        meme_img = await self._generate_meme(ctx, member)

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

    @subcommand("reddit")
    @slash_command(
        name="shitpost", description="Random post from various shitposting subreddits."
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def shitpost(self, ctx: discord.ApplicationContext) -> None:
        await self.process_shitpost(ctx)

    async def process_shitpost(self, ctx: discord.ApplicationContext) -> None:
        user_id = ctx.author.id
        user_data, temp_user_data = await self._load_user_data(ctx)

        multireddit: asyncpraw.models.Multireddit = temp_user_data["multireddit"]
        limit = temp_user_data["search_limit"]

        try:
            async for submission in multireddit.hot(limit=limit):
                is_valid = await self._is_valid_submission(
                    submission, user_data, temp_user_data
                )
                if not is_valid:
                    continue

                is_channel_nsfw = ctx.channel.is_nsfw()
                if submission.over_18 and not is_channel_nsfw:
                    await send_response(ctx, "CHANNEL_NOT_NSFW")
                    return

                embed = await self._create_reddit_embed(submission)

                if submission.media:
                    await ctx.respond(embed=embed)
                    await self._post_video(ctx, submission.permalink)
                # If it has multiple images
                elif hasattr(submission, "gallery_data"):
                    await ctx.respond(embed=embed)
                    await self._send_multiple_images(ctx, submission)
                else:
                    embed.set_image(url=submission.url)
                    await ctx.respond(embed=embed)

                self._update_temp_user_data(user_id, submission.permalink)
                break

        except (AsyncPrawcoreException, RequestException, ResponseException) as e:
            print(e)
            print(vars(e))
            await send_response(ctx, "REDDIT_REQUEST_ERROR")

    def _update_temp_user_data(self, user_id: int, submission_url: str) -> None:
        self.temp_user_data[user_id]["reddit"]["viewed_posts"].add(submission_url)
        self.temp_user_data[user_id]["reddit"]["last_used"] = datetime.now()
        self.temp_user_data[user_id]["reddit"]["search_limit"] += 1

    async def _load_user_data(self, ctx: discord.ApplicationContext) -> tuple:
        user_data, temp_user_data = await get_user_data(
            self.bot,
            ctx,
        )
        return user_data["reddit"], temp_user_data["reddit"]

    async def _create_reddit_embed(
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

    async def _generate_meme(
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
    async def _is_valid_submission(
        submission: asyncpraw.models.Submission,
        user_data: dict,
        temp_user_data: dict,
    ) -> bool:
        # If post is locked, or is stickied, or it's a poll, skip it
        if submission.locked or submission.stickied or hasattr(submission, "poll_data"):
            return False

        if submission.permalink in temp_user_data["viewed_posts"]:
            return False

        nsfw_posts: bool = user_data["nsfw_posts"]
        if submission.over_18 and not nsfw_posts:
            return False

        return True

    async def _get_jokes(self) -> list[str] | None:
        fetched_jokes: list[str] = []
        jokes = await self._get_humor_api_jokes()
        if jokes:
            fetched_jokes.extend(jokes)

        jokes = await self._get_joke_api_jokes()
        if jokes:
            fetched_jokes.extend(jokes)

        return fetched_jokes

    async def _get_dadjokes(self) -> list[str] | None:
        fetched_jokes: list[str] = []
        response = await make_http_request(
            self.session,
            DAD_JOKE_API_URL,
            retries=3,
            headers={"Accept": "application/json"},
            get_json=True,
        )
        if not response:
            return None

        jokes = response.get("results")
        if not jokes:
            return None

        for joke in jokes:
            joke = joke.get("joke")
            if joke in self.loaded_dad_jokes:
                continue

            fetched_jokes.append(joke)
        return fetched_jokes

    async def _get_yo_mama_jokes(self) -> list[str] | None:
        token = self._load_humor_api_token()
        fetched_jokes: list[str] = []
        if self.bot.humor_api_tokens[token]["exhausted"]:
            return None

        for _ in range(len(self.bot.humor_api_tokens)):
            response = await make_http_request(
                self.session,
                HUMOR_API_URL + f"yo_mama&api-key={token}&max-length=256",
            )
            token = self.is_token_exhausted(response, token)
            if not token:
                continue
            break

        jokes = response.json()
        for joke in jokes["jokes"]:
            if joke.get("joke") in self.loaded_yo_mama_jokes:
                continue

            fetched_jokes.append(joke.get("joke"))

        return fetched_jokes

    async def _get_joke_api_jokes(self) -> list[str] | None:
        fetched_jokes: list[str] = []
        response = await make_http_request(
            self.session,
            JOKE_API_URL,
            get_json=True,
        )
        if not response:
            return None

        if response.get("error"):
            return None

        jokes = response.get("jokes")
        if not jokes:
            return None

        for joke in jokes:
            joke = (
                f"{joke.get('setup')}\n{joke.get('delivery')}"
                if joke.get("type") == "twopart"
                else joke.get("joke")
            )
            if joke in self.loaded_jokes:
                continue

            is_filtered = [k for k in JOKE_EXCLUDED_WORDS if k in joke]
            if is_filtered:
                continue

            fetched_jokes.append(joke)

        return fetched_jokes

    async def _get_humor_api_jokes(self) -> list[str] | None:
        token = self._load_humor_api_token()
        fetched_jokes: list[str] = []
        if self.bot.humor_api_tokens[token]["exhausted"]:
            return None

        for joke_type in ["racist", "jewish"]:
            for _ in range(len(self.bot.humor_api_tokens)):
                response = await make_http_request(
                    self.session,
                    HUMOR_API_URL + f"{joke_type}&api-key={token}&max-length=256",
                    retries=3,
                )
                token = self.is_token_exhausted(response, token)
                if not token:
                    continue
                break

            jokes = response.json()
            for joke in jokes["jokes"]:
                if joke.get("joke") in self.loaded_jokes:
                    continue

                is_filtered = [k for k in JOKE_EXCLUDED_WORDS if k in joke.get("joke")]
                if is_filtered:
                    continue

                fetched_jokes.append(joke.get("joke"))

        return fetched_jokes

    def _load_humor_api_token(self) -> str | None:
        for token in self.bot.humor_api_tokens:
            if self.bot.humor_api_tokens[token].get("exhausted"):
                continue
            return token
        return None

    def is_token_exhausted(self, response: httpx.Response, token) -> str | None:
        if not response:
            self.bot.humor_api_tokens[token]["exhausted"] = True
            return self._load_humor_api_token()

        quota_left = response.headers.get("x-api-quota-left")
        if quota_left == "0":
            self.bot.humor_api_tokens[token]["exhausted"] = True
            return self._load_humor_api_token()

        return token

    @staticmethod
    async def _send_multiple_images(
        ctx: discord.ApplicationContext, submission: asyncpraw.reddit.Submission
    ) -> None:
        for images in submission.gallery_data["items"]:
            await ctx.send(f"https://i.redd.it/{images['media_id']}.jpg")

    @staticmethod
    async def _post_video(ctx: discord.ApplicationContext, submission_url: str) -> None:
        video_url = submission_url.split("/")[4]
        await ctx.send(f"https://rxddit.com/{video_url}/", suppress=False)


def setup(bot: commands.Bot):
    bot.add_cog(FunCommands(bot))
