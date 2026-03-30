import random
from datetime import datetime
from typing import Optional

import asyncpraw.models
import asyncpraw.reddit
import discord
import httpx
from asyncprawcore.exceptions import (
    AsyncPrawcoreException,
    RequestException,
    ResponseException,
)
from discord import app_commands
from discord.ext import commands

from app.constants import API_DAD_JOKE, API_HUMORAPI, API_JOKEAPI, JOKE_EXCLUDED_WORDS
from app.response_handler import defer_interaction, send_interaction, send_response
from app.utils import get_guild_data, get_user_data, load_text_file, make_http_request


async def is_valid_submission(
    submission: asyncpraw.models.Submission,
    user_data: dict,
    temp_user_data: dict,
) -> bool:
    """Validate whether a Reddit submission should be processed."""
    if submission.locked or submission.stickied or hasattr(submission, "poll_data"):
        return False

    if submission.permalink in temp_user_data["viewed_posts"]:
        return False

    nsfw_posts: bool = user_data["nsfw_posts"]
    if submission.over_18 and not nsfw_posts:
        return False

    return True


async def send_multiple_images(
    ctx: discord.Interaction, submission: asyncpraw.reddit.Submission
) -> None:
    for image in submission.gallery_data["items"]:
        await send_interaction(ctx, f"https://i.redd.it/{image['media_id']}.jpg")


async def post_video(ctx: discord.Interaction, submission_url: str) -> None:
    video_url = submission_url.split("/")[4]
    await send_interaction(ctx, f"https://rxddit.com/{video_url}/", suppress=False)


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

    @app_commands.command(
        name="kotrmelec",
        description="Legendárne školské kotrmelce",
    )
    async def kotrmelec(self, ctx: discord.Interaction) -> None:
        """This command sends a random "kotrmelec" message from a file.

        This command is restricted to specific guilds because it's private.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command.
        """
        await send_interaction(ctx, random.choice(self._kotrmelce))

    @app_commands.command(
        name="topstropscreenshot",
        description="Topové fotečky z online hodín",
    )
    async def top_strop_screenshot(self, ctx: discord.Interaction) -> None:
        """This command sends a random screenshot from a file.

        This command is restricted to specific guilds because it's private.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command.
        """
        await send_interaction(ctx, random.choice(self._topstropscreenshot))

    # -------------------- Joke commands -------------------- #
    @app_commands.command(name="joke", description="Fetches random joke.")
    @app_commands.checks.cooldown(1, 3, key=lambda i: i.user.id)
    async def joke(self, ctx: discord.Interaction) -> None:
        """This command fetches a random joke from the loaded jokes.

        If all jokes have been viewed, it fetches new jokes from the API.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command.
        """
        _, temp_guild_data = await get_guild_data(self._bot, ctx.guild.id)
        viewed_count = len(temp_guild_data["jokes"]["viewed_jokes"])
        loaded_count = len(self._loaded_jokes)

        if (viewed_count == 0 and loaded_count == 0) or viewed_count == loaded_count:
            await defer_interaction(ctx)
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
        self._temp_guild_data[ctx.guild.id] = temp_guild_data

        joke = discord.utils.escape_markdown(joke)
        await send_interaction(ctx, joke)

    @app_commands.command(name="dad_joke", description="Fetches random dad joke.")
    @app_commands.checks.cooldown(1, 3, key=lambda i: i.user.id)
    async def dad_joke(self, ctx: discord.Interaction) -> None:
        """This command fetches a random dad joke from the loaded dad jokes.

        If all dad jokes have been viewed, it fetches new dad jokes from the API.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command.
        """
        _, temp_guild_data = await get_guild_data(self._bot, ctx.guild.id)
        viewed_count = len(temp_guild_data["jokes"]["viewed_dad_jokes"])
        loaded_count = len(self._loaded_dad_jokes)

        if (viewed_count == 0 and loaded_count == 0) or viewed_count == loaded_count:
            await defer_interaction(ctx)
            jokes = await self._get_dad_jokes()
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
        self._temp_guild_data[ctx.guild.id] = temp_guild_data

        joke = discord.utils.escape_markdown(joke)
        await send_interaction(ctx, joke)

    @app_commands.command(
        name="yo_mama",
        description="Yo mama joke on a discord member.",
    )
    @app_commands.describe(member="Discord member to roast.")
    @app_commands.checks.cooldown(1, 3, key=lambda i: i.user.id)
    async def yo_mama(self, ctx: discord.Interaction, member: discord.Member) -> None:
        """This command fetches a random yo mama joke and targets a member.

        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command.
        member: :class:`discord.Member`
            The member to roast.
        """
        _, temp_guild_data = await get_guild_data(self._bot, ctx.guild.id)
        viewed_count = len(temp_guild_data["jokes"]["viewed_yo_mama_jokes"])
        loaded_count = len(self._loaded_yo_mama_jokes)

        if (viewed_count == 0 and loaded_count == 0) or viewed_count == loaded_count:
            await defer_interaction(ctx)
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
        self._temp_guild_data[ctx.guild.id] = temp_guild_data

        joke = joke[0].lower() + joke[1:] if joke else ""
        joke = discord.utils.escape_markdown(joke)

        target = member
        if self._bot.user and member.id == self._bot.user.id:
            target = ctx.user

        await send_interaction(ctx, f"{target.mention} {joke}")

    @app_commands.command(
        name="shitpost",
        description="Random post from configured shitposting subreddits.",
    )
    @app_commands.checks.cooldown(1, 5, key=lambda i: i.user.id)
    async def shitpost(self, ctx: discord.Interaction) -> None:
        await self.process_shitpost(ctx)

    async def process_shitpost(self, ctx: discord.Interaction) -> None:
        """This command fetches a random post from various shitposting subreddits.
        It checks if the post is valid and not already viewed. If the post is NSFW,
        it checks if the channel is NSFW. If the post is valid, it sends the post
        as an embed and updates the viewed posts in the user data.
        Parameters
        ----------
        ctx: :class:`discord.Interaction`
            The context of the command.
        """
        user_id = ctx.user.id
        user_data, temp_user_data = await self._load_user_data(ctx)

        multireddit: asyncpraw.models.Multireddit = temp_user_data["multireddit"]
        limit = temp_user_data["search_limit"]

        try:
            async for submission in multireddit.hot(limit=limit):
                is_valid = await is_valid_submission(
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
                    await send_interaction(ctx, embed=embed)
                    await post_video(ctx, submission.permalink)
                # If it has multiple images
                elif hasattr(submission, "gallery_data"):
                    await send_interaction(ctx, embed=embed)
                    await send_multiple_images(ctx, submission)
                else:
                    embed.set_image(url=submission.url)
                    await send_interaction(ctx, embed=embed)

                self._update_temp_user_data(user_id, submission.permalink)
                break

        except (
            AsyncPrawcoreException,
            RequestException,
            ResponseException,
        ):
            await send_response(ctx, "REDDIT_REQUEST_ERROR")

    def _update_temp_user_data(self, user_id: int, submission_url: str) -> None:
        self._temp_user_data[user_id]["reddit"]["viewed_posts"].add(submission_url)
        self._temp_user_data[user_id]["reddit"]["last_used"] = datetime.now()
        self._temp_user_data[user_id]["reddit"]["search_limit"] += 1

    async def _load_user_data(self, ctx: discord.Interaction) -> tuple[dict, dict]:
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

    async def _get_jokes(self) -> Optional[list[str]]:
        fetched_jokes: list[str] = []
        jokes = await self._get_humor_api_jokes()
        fetched_jokes.extend(jokes)

        jokes = await self._get_joke_api_jokes()
        fetched_jokes.extend(jokes)

        return fetched_jokes

    async def _get_dad_jokes(self) -> Optional[list[str]]:
        fetched_jokes: list[str] = []
        response = await make_http_request(
            self._session,
            API_DAD_JOKE,
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
        if not token or self._bot.humor_api_tokens[token]["exhausted"]:
            return None

        response = None
        for _ in range(len(self._bot.humor_api_tokens)):
            response = await make_http_request(
                self._session,
                API_HUMORAPI + f"yo_mama&api-key={token}&max-length=256",
                retries=3,
            )
            token = self._is_token_exhausted(response, token)
            if token:
                break
            token = self._load_humor_api_token()

        if not response:
            return None

        jokes = response.json()
        for joke in jokes.get("jokes", []):
            text = joke.get("joke")
            if not text or text in self._loaded_yo_mama_jokes:
                continue

            fetched_jokes.append(text)

        return fetched_jokes

    async def _get_joke_api_jokes(self) -> list[str]:
        fetched_jokes: list[str] = []
        response = await make_http_request(
            self._session,
            API_JOKEAPI,
            get_json=True,
        )
        if not response:
            return []

        if response.get("error"):
            return []

        jokes = response.get("jokes")
        if not jokes:
            return []

        for joke in jokes:
            joke_text: str = (
                f"{joke.get('setup')}\n{joke.get('delivery')}"
                if joke.get("type") == "twopart"
                else joke.get("joke")
            )
            if not joke_text or joke_text in self._loaded_jokes:
                continue

            if any(word in joke_text.lower().split() for word in JOKE_EXCLUDED_WORDS):
                continue

            fetched_jokes.append(joke_text)

        return fetched_jokes

    async def _get_humor_api_jokes(self) -> list[str]:
        fetched_jokes: list[str] = []

        for joke_type in ["racist", "jewish", "nsfw"]:
            token = self._load_humor_api_token()
            if not token or self._bot.humor_api_tokens[token]["exhausted"]:
                break

            response = None
            for _ in range(len(self._bot.humor_api_tokens)):
                response = await make_http_request(
                    self._session,
                    API_HUMORAPI + f"{joke_type}&api-key={token}&max-length=256",
                    retries=3,
                )
                token = self._is_token_exhausted(response, token)
                if token:
                    break
                token = self._load_humor_api_token()

            if not response:
                continue

            jokes = response.json()
            for joke in jokes.get("jokes", []):
                text = joke.get("joke")
                if not text or text in self._loaded_jokes:
                    continue

                if any(k in text.lower().split() for k in JOKE_EXCLUDED_WORDS):
                    continue

                fetched_jokes.append(text)

        return fetched_jokes

    def _load_humor_api_token(self) -> Optional[str]:
        for token in self._bot.humor_api_tokens:
            if self._bot.humor_api_tokens[token].get("exhausted"):
                continue
            return token
        return None

    def _is_token_exhausted(
        self, response: Optional[httpx.Response], token: Optional[str]
    ) -> Optional[str]:
        if not token:
            return None

        if not response:
            self._bot.humor_api_tokens[token]["exhausted"] = True
            return None

        quota_left = response.headers.get("x-api-quota-left")
        if quota_left == "0":
            self._bot.humor_api_tokens[token]["exhausted"] = True
            return None

        return token


async def setup(bot: commands.Bot):
    """This function sets up the FunCommands cog."""
    await bot.add_cog(FunCommands(bot))
