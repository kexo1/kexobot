import random
from datetime import datetime
from typing import Optional

import asyncpraw.models
import asyncpraw.reddit
import discord
import httpx
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
    """Fun commands for the bot.

    This class contains various fun commands for the bot, including jokes,
    memes, and other humorous content. It also handles the loading of jokes
    from external APIs and manages the state of viewed jokes to avoid
    repetition.

    Parameters
    ----------
    bot: :class:`commands.Bot`
        The bot instance that this cog is associated with.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self._bot = bot
        self._bot_config = self._bot.bot_config
        self._user_data_db = self._bot.user_data_db

        self._user_data = self._bot.user_data
        self._temp_user_data = self._bot.temp_user_data
        self._temp_guild_data = self._bot.temp_guild_data
        self._reddit_agent = self._bot.reddit_agent
        self._session: httpx.AsyncClient = self._bot.session

        self._loaded_jokes: list[str] = self._bot.loaded_jokes
        self._loaded_dad_jokes: list[str] = self._bot.loaded_dad_jokes
        self._loaded_yo_mama_jokes: list[str] = self._bot.loaded_yo_mama_jokes

        self._topstropscreenshot = load_text_file("topstropscreenshot")
        self._kotrmelce = load_text_file("kotrmelec")
        self._idk_count = 0

    @slash_command(
        name="kotrmelec",
        description="Legendárne školské kotrmelce",
        guild_ids=[KEXO_SERVER, SISKA_GANG_SERVER],
    )
    async def kotrmelec(self, ctx: discord.ApplicationContext) -> None:
        """This command sends a random "kotrmelec" message from a file.

        This command is restricted to specific guilds because it's private.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command.
        """
        await ctx.respond(random.choice(self._kotrmelce))

    @slash_command(
        name="topstropscreenshot",
        description="Topové fotečky z online hodín",
        guild_ids=[KEXO_SERVER, SISKA_GANG_SERVER],
    )
    async def top_strop_screenshot(self, ctx: discord.ApplicationContext) -> None:
        """This command sends a random screenshot from a file.

        This command is restricted to specific guilds because it's private.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command.
        """
        await ctx.respond(random.choice(self._topstropscreenshot))

    @slash_command(
        name="roast",
        description="Lamar roast",
        guild_ids=[KEXO_SERVER, SISKA_GANG_SERVER],
    )
    async def roast(self, ctx: discord.ApplicationContext) -> None:
        """This command sends a Lamar roast from GTAV.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command.
        """

        await ctx.respond(ROAST_COMMANDS_MSG)

    # -------------------- Joke commands -------------------- #
    @slash_command(name="joke", description="Fetches random joke.")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def joke(self, ctx: discord.ApplicationContext) -> None:
        """This command fetches a random joke from the loaded jokes.

        If all jokes have been viewed, it fetches new jokes from the API.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command.
        """
        _, temp_guild_data = await get_guild_data(self._bot, ctx.guild_id)
        viewed_count = len(temp_guild_data["jokes"]["viewed_jokes"])
        loaded_count = len(self._loaded_jokes)

        if (viewed_count == 0 and loaded_count == 0) or viewed_count == loaded_count:
            await ctx.defer()
            jokes = await self._get_jokes()
            if not jokes:
                await send_response(ctx, "JOKE_TIMEOUT")
                return

            self._loaded_jokes.extend(jokes)
            random.shuffle(self._loaded_jokes)

        joke = None
        for joke in self._loaded_jokes:
            if joke in temp_guild_data["jokes"]["viewed_jokes"]:
                continue
            break

        if not joke:
            await send_response(ctx, "NO_MORE_JOKES")
            return

        temp_guild_data["jokes"]["viewed_jokes"].append(joke)
        self._temp_guild_data[ctx.guild_id] = temp_guild_data

        joke = escape_markdown(joke)
        await ctx.respond(joke)

    @slash_command(name="dad_joke", description="Fetches random dad joke.")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def dad_joke(self, ctx: discord.ApplicationContext) -> None:
        """This command fetches a random dad joke from the loaded dad jokes.

        If all dad jokes have been viewed, it fetches new dad jokes from the API.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command.
        """
        _, temp_guild_data = await get_guild_data(self._bot, ctx.guild_id)
        viewed_count = len(temp_guild_data["jokes"]["viewed_dad_jokes"])
        loaded_count = len(self._loaded_dad_jokes)

        if (viewed_count == 0 and loaded_count == 0) or viewed_count == loaded_count:
            await ctx.defer()
            jokes = await self._get_dadjokes()
            if not jokes:
                await send_response(ctx, "JOKE_TIMEOUT")
                return

            self._loaded_dad_jokes.extend(jokes)
            random.shuffle(self._loaded_dad_jokes)

        joke = None
        for joke in self._loaded_dad_jokes:
            if joke in temp_guild_data["jokes"]["viewed_dad_jokes"]:
                continue
            break

        if not joke:
            await send_response(ctx, "NO_MORE_JOKES")
            return

        temp_guild_data["jokes"]["viewed_dad_jokes"].append(joke)
        self._temp_guild_data[ctx.guild_id] = temp_guild_data

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
        """This command fetches a random yo mama joke from the loaded yo mama jokes.

        If all yo mama jokes have been viewed, it fetches new yo mama jokes from the API.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command.
        member: :class:`discord.Member`
            member to roast.
        """
        _, temp_guild_data = await get_guild_data(self._bot, ctx.guild_id)
        viewed_count = len(temp_guild_data["jokes"]["viewed_yo_mama_jokes"])
        loaded_count = len(self._loaded_yo_mama_jokes)

        if (viewed_count == 0 and loaded_count == 0) or viewed_count == loaded_count:
            await ctx.defer()
            jokes = await self._get_yo_mama_jokes()
            if not jokes:
                await send_response(ctx, "JOKE_TIMEOUT")
                return

            self._loaded_yo_mama_jokes.extend(jokes)
            random.shuffle(self._loaded_yo_mama_jokes)

        joke = None
        for joke in self._loaded_yo_mama_jokes:
            if joke in temp_guild_data["jokes"]["viewed_yo_mama_jokes"]:
                continue
            break

        if not joke:
            await send_response(ctx, "NO_MORE_JOKES")
            return

        temp_guild_data["jokes"]["viewed_yo_mama_jokes"].append(joke)
        self._temp_guild_data[ctx.guild_id] = temp_guild_data

        joke = joke[0].lower() + joke[1:]
        joke = escape_markdown(joke)
        if member.name == "KexoBOT":
            await ctx.respond(ctx.author.mention + " " + joke)
        else:
            await ctx.respond(member.mention + " " + joke)

    @slash_command(name="spam", description="Spams words, max is 50.  (Admin)")
    @discord.default_permissions(administrator=True)
    @commands.cooldown(1, 50, commands.BucketType.user)
    @option("integer", description="Max is 50.", min_value=1, max_value=50)
    async def spam(
        self, ctx: discord.ApplicationContext, word: str, integer: int
    ) -> None:
        """This command spams a word a specified number of times.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command.
        word: str
            The word to spam.
        integer: int
            The number of times to spam the word.
        """
        await ctx.respond(word)
        for _ in range(integer - 1):
            await ctx.send(word)

    @slash_command(
        name="idk", description="Idk.", guild_ids=[KEXO_SERVER, SISKA_GANG_SERVER]
    )
    async def idk(self, ctx: discord.ApplicationContext) -> None:
        """This command sends a random "idk" message.

        After 5 times, it sends a jumpscare.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command.
        """
        self._idk_count += 1
        if self._idk_count < 5:
            await ctx.respond("idk")
            return
        await ctx.respond(
            "https://media.discordapp.net/attachments"
            "/796453724713123870/1042486203842306159/image.png"
        )
        self._idk_count = 0

    @subcommand("reddit")
    @slash_command(
        name="shitpost", description="Random post from various shitposting subreddits."
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def shitpost(self, ctx: discord.ApplicationContext) -> None:
        """This command cals a method which fetches
         a random post from various shitposting subreddits.

        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command.
        """
        await self.process_shitpost(ctx)

    async def process_shitpost(self, ctx: discord.ApplicationContext) -> None:
        """This command fetches a random post from various shitposting subreddits.
        It checks if the post is valid and not already viewed. If the post is NSFW,
        it checks if the channel is NSFW. If the post is valid, it sends the post
        as an embed and updates the viewed posts in the user data.
        Parameters
        ----------
        ctx: :class:`discord.ApplicationContext`
            The context of the command.
        """
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
        self._temp_user_data[user_id]["reddit"]["viewed_posts"].add(submission_url)
        self._temp_user_data[user_id]["reddit"]["last_used"] = datetime.now()
        self._temp_user_data[user_id]["reddit"]["search_limit"] += 1

    async def _load_user_data(self, ctx: discord.ApplicationContext) -> tuple:
        user_data, temp_user_data = await get_user_data(
            self._bot,
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
            icon_url=self._bot.subreddit_icons[subreddit.display_name],
        )
        embed.timestamp = datetime.fromtimestamp(submission.created_utc)
        return embed

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

    async def _get_jokes(self) -> Optional[list[str]]:
        fetched_jokes: list[str] = []
        jokes = await self._get_humor_api_jokes()
        if jokes:
            fetched_jokes.extend(jokes)

        jokes = await self._get_joke_api_jokes()
        if jokes:
            fetched_jokes.extend(jokes)

        return fetched_jokes

    async def _get_dadjokes(self) -> Optional[list[str]]:
        fetched_jokes: list[str] = []
        response = await make_http_request(
            self._session,
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
            if joke in self._loaded_dad_jokes:
                continue

            fetched_jokes.append(joke)
        return fetched_jokes

    async def _get_yo_mama_jokes(self) -> Optional[list[str]]:
        token = self._load_humor_api_token()
        fetched_jokes: list[str] = []
        if self._bot.humor_api_tokens[token]["exhausted"]:
            return None

        for _ in range(len(self._bot.humor_api_tokens)):
            response = await make_http_request(
                self._session,
                HUMOR_API_URL + f"yo_mama&api-key={token}&max-length=256",
            )
            token = self._is_token_exhausted(response, token)
            if not token:
                token = self._load_humor_api_token()
                continue
            break

        jokes = response.json()
        for joke in jokes["jokes"]:
            if joke.get("joke") in self._loaded_yo_mama_jokes:
                continue

            fetched_jokes.append(joke.get("joke"))

        return fetched_jokes

    async def _get_joke_api_jokes(self) -> Optional[list[str]]:
        fetched_jokes: list[str] = []
        response = await make_http_request(
            self._session,
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
            joke: str = (
                f"{joke.get('setup')}\n{joke.get('delivery')}"
                if joke.get("type") == "twopart"
                else joke.get("joke")
            )
            if joke in self._loaded_jokes:
                continue

            is_filtered = [k for k in JOKE_EXCLUDED_WORDS if k in joke.lower().split()]
            if is_filtered:
                continue

            fetched_jokes.append(joke)

        return fetched_jokes

    async def _get_humor_api_jokes(self) -> Optional[list[str]]:
        token = self._load_humor_api_token()
        fetched_jokes: list[str] = []
        if self._bot.humor_api_tokens[token]["exhausted"]:
            return None

        for joke_type in ["racist", "jewish"]:
            for _ in range(len(self._bot.humor_api_tokens)):
                response = await make_http_request(
                    self._session,
                    HUMOR_API_URL + f"{joke_type}&api-key={token}&max-length=256",
                    retries=3,
                )
                token = self._is_token_exhausted(response, token)
                if not token:
                    token = self._load_humor_api_token()
                    continue
                break

            jokes = response.json()
            for joke in jokes["jokes"]:
                if joke.get("joke") in self._loaded_jokes:
                    continue

                is_filtered = [
                    k
                    for k in JOKE_EXCLUDED_WORDS
                    if k in joke.get("joke").lower().split()
                ]
                if is_filtered:
                    continue

                fetched_jokes.append(joke.get("joke"))

        return fetched_jokes

    def _load_humor_api_token(self) -> Optional[str]:
        for token in self._bot.humor_api_tokens:
            if self._bot.humor_api_tokens[token].get("exhausted"):
                continue
            return token
        return None

    def _is_token_exhausted(self, response: httpx.Response, token) -> Optional[str]:
        if not response:
            self._bot.humor_api_tokens[token]["exhausted"] = True
            return None

        quota_left = response.headers.get("x-api-quota-left")
        if quota_left == "0":
            self._bot.humor_api_tokens[token]["exhausted"] = True
            return None

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
    """This function sets up the FunCommands cog."""
    bot.add_cog(FunCommands(bot))
