import logging
import random
from datetime import datetime
from typing import TYPE_CHECKING, Optional

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

from app.config.scraping import API_DAD_JOKE, API_HUMORAPI, API_JOKEAPI
from app.data.models import TempUserRedditData, UserRedditData
from app.response_handler import defer_interaction, make_embed, send
from app.utils import load_text_file, make_http_request

if TYPE_CHECKING:
    from app.main import KexoBotClient


async def send_multiple_images(
    ctx: discord.Interaction, submission: asyncpraw.reddit.Submission
) -> None:
    for image in submission.gallery_data["items"]:
        await send(ctx, f"https://i.redd.it/{image['media_id']}.jpg")


async def post_video(ctx: discord.Interaction, submission_url: str) -> None:
    await send(ctx, f"https://vxreddit.com{submission_url}", suppress=False)


def is_valid_submission(
    submission: asyncpraw.models.Submission,
    user_reddit: UserRedditData,
    temp_user_reddit: TempUserRedditData,
) -> bool:
    """Validate whether a Reddit submission should be processed."""
    if submission.locked or submission.stickied or hasattr(submission, "poll_data"):
        return False

    if submission.permalink in temp_user_reddit.viewed_posts:
        return False

    if submission.over_18 and not user_reddit.nsfw_posts:
        return False

    return True


class FunCommands(commands.Cog):
    """Fun commands for the bot.

    This class contains various fun commands for the bot, including jokes,
    memes, and other humorous content. It also handles the loading of jokes
    from external APIs and manages the state of viewed jokes to avoid
    repetition.

    Parameters
    ----------
    bot: :class:`KexoBotClient`
        The bot instance that this cog is associated with.
    """

    def __init__(self, bot: "KexoBotClient") -> None:
        self._bot = bot
        self._bot_config = self._bot.bot_config
        self._user_mgr = self._bot.user_data_manager
        self._temp_user_mgr = self._bot.temp_user_data_manager
        self._temp_guild_mgr = self._bot.temp_guild_data_manager
        self._joke_cache = self._bot.joke_cache_manager
        self._reddit_agent = self._bot.reddit_agent
        self._session: httpx.AsyncClient = self._bot.session

        self._loaded_jokes: set[str] = self._joke_cache.loaded_jokes
        self._loaded_dad_jokes: set[str] = self._joke_cache.loaded_dad_jokes
        self._loaded_yo_mama_jokes: set[str] = self._joke_cache.loaded_yo_mama_jokes

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
        await send(ctx, random.choice(self._kotrmelce))

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
        await send(ctx, random.choice(self._topstropscreenshot))

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
        temp_guild = self._temp_guild_mgr.get(ctx.guild.id)
        viewed_count = len(temp_guild.jokes.viewed_jokes)
        loaded_count = len(self._loaded_jokes)

        if (viewed_count == 0 and loaded_count == 0) or viewed_count == loaded_count:
            await defer_interaction(ctx)
            jokes = await self._get_jokes()
            if not jokes:
                await send(ctx, code="JOKE_TIMEOUT")
                return

            self._loaded_jokes.update(jokes)

        joke = None
        for joke in self._loaded_jokes:
            if joke in temp_guild.jokes.viewed_jokes:
                continue
            break

        if not joke:
            await send(ctx, code="NO_MORE_JOKES")
            return

        temp_guild.jokes.viewed_jokes.append(joke)
        joke = discord.utils.escape_markdown(joke)
        await send(ctx, joke)

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
        temp_guild = self._temp_guild_mgr.get(ctx.guild.id)
        viewed_count = len(temp_guild.jokes.viewed_dad_jokes)
        loaded_count = len(self._loaded_dad_jokes)

        if (viewed_count == 0 and loaded_count == 0) or viewed_count == loaded_count:
            await defer_interaction(ctx)
            jokes = await self._get_dad_jokes()
            if not jokes:
                await send(ctx, code="JOKE_TIMEOUT")
                return

            self._loaded_dad_jokes.update(jokes)

        joke = None
        for joke in self._loaded_dad_jokes:
            if joke in temp_guild.jokes.viewed_dad_jokes:
                continue
            break

        if not joke:
            await send(ctx, code="NO_MORE_JOKES")
            return

        temp_guild.jokes.viewed_dad_jokes.append(joke)

        joke = discord.utils.escape_markdown(joke)
        await send(ctx, joke)

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
        temp_guild = self._temp_guild_mgr.get(ctx.guild.id)
        viewed_count = len(temp_guild.jokes.viewed_yo_mama_jokes)
        loaded_count = len(self._loaded_yo_mama_jokes)

        if (viewed_count == 0 and loaded_count == 0) or viewed_count == loaded_count:
            await defer_interaction(ctx)
            jokes = await self._get_yo_mama_jokes()
            if not jokes:
                await send(ctx, code="JOKE_TIMEOUT")
                return

            self._loaded_yo_mama_jokes.update(jokes)

        joke = None
        for joke in self._loaded_yo_mama_jokes:
            if joke in temp_guild.jokes.viewed_yo_mama_jokes:
                continue
            break

        if not joke:
            await send(ctx, code="NO_MORE_JOKES")
            return

        temp_guild.jokes.viewed_yo_mama_jokes.append(joke)

        joke = joke[0].lower() + joke[1:] if joke else ""
        joke = discord.utils.escape_markdown(joke)

        target = member
        if self._bot.user and member.id == self._bot.user.id:
            target = ctx.user

        await send(ctx, f"{target.mention} {joke}")

    @app_commands.command(
        name="shitpost",
        description="Random post from configured shitposting subreddits.",
    )
    @app_commands.checks.cooldown(1, 5, key=lambda i: i.user.id)
    async def shitpost(self, ctx: discord.Interaction) -> None:
        await defer_interaction(ctx)
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
        user_reddit, temp_user_reddit = await self._load_user_data(user_id)
        multireddit = temp_user_reddit.multireddit
        limit = temp_user_reddit.search_limit

        if not temp_user_reddit.multireddit:
            await send(ctx, "REDDIT_CANT_LOAD_MULTIREDDIT")
            return

        multireddit = temp_user_reddit.multireddit
        limit = temp_user_reddit.search_limit

        try:
            async for submission in multireddit.hot(limit=limit):
                if not is_valid_submission(submission, user_reddit, temp_user_reddit):
                    continue

                is_channel_nsfw = ctx.channel.is_nsfw()
                if submission.over_18 and not is_channel_nsfw:
                    await send(
                        ctx,
                        embed=make_embed(
                            ":x: This post is NSFW, use the command in an NSFW channel."
                        ),
                    )
                    return

                if not submission.media:
                    embed = await self._create_reddit_embed(submission)

                if submission.media:
                    await post_video(ctx, submission.permalink)
                # If it has multiple images
                elif hasattr(submission, "gallery_data"):
                    await send(ctx, embed=embed)
                    await send_multiple_images(ctx, submission)
                else:
                    embed.set_image(url=submission.url)
                    await send(ctx, embed=embed)

                self._update_temp_user_data(user_id, submission.permalink)
                break

        except (
            AsyncPrawcoreException,
            RequestException,
            ResponseException,
        ):
            await send(
                ctx,
                embed=make_embed(
                    ":x: Failed to get post from Reddit, try again later.",
                    color=discord.Color.from_rgb(r=220, g=0, b=0),
                ),
            )

        if len(temp_user_reddit.viewed_posts) >= len(user_reddit.subreddits):
            temp_user_reddit.search_limit = min(50, temp_user_reddit.search_limit + 1)

    async def _load_user_data(self, user_id: int) -> tuple[UserRedditData, TempUserRedditData]:
        """Load user and temp user data, ensuring multireddit exists."""
        user = await self._user_mgr.get(user_id)
        temp = self._temp_user_mgr.get(user_id)

        if temp.reddit.multireddit is None:
            await self._temp_user_mgr.ensure_multireddit(user_id)

        return user.reddit, temp.reddit

    def _update_temp_user_data(self, user_id: int, submission_url: str) -> None:
        temp = self._temp_user_mgr.get(user_id)
        temp.reddit.viewed_posts.add(submission_url)
        temp.reddit.last_used = datetime.now()
        logging.info(f"User {user_id} viewed posts: {temp.reddit.viewed_posts}")

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

    async def _get_jokes(self) -> Optional[set[str]]:
        fetched_jokes: set[str] = set()
        jokes = await self._get_humor_api_jokes()
        fetched_jokes.update(jokes)

        jokes = await self._get_joke_api_jokes()
        fetched_jokes.update(jokes)

        return fetched_jokes

    async def _get_dad_jokes(self) -> Optional[set[str]]:
        fetched_jokes: set[str] = set()
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

            fetched_jokes.add(joke)
        return fetched_jokes

    async def _get_yo_mama_jokes(self) -> Optional[set[str]]:
        token = self._load_humor_api_token()
        fetched_jokes: set[str] = set()
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

            fetched_jokes.add(text)

        return fetched_jokes

    async def _get_joke_api_jokes(self) -> set[str]:
        fetched_jokes: set[str] = set()
        response = await make_http_request(
            self._session,
            API_JOKEAPI,
            get_json=True,
        )
        if not response:
            return set()

        if response.get("error"):
            return set()

        jokes = response.get("jokes")
        if not jokes:
            return set()

        for joke in jokes:
            joke_text: str = (
                f"{joke.get('setup')}\n{joke.get('delivery')}"
                if joke.get("type") == "twopart"
                else joke.get("joke")
            )
            if not joke_text or joke_text in self._loaded_jokes:
                continue

            fetched_jokes.add(joke_text)

        return fetched_jokes

    async def _get_humor_api_jokes(self) -> set[str]:
        fetched_jokes: set[str] = set()

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

                fetched_jokes.add(text)

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


async def setup(bot: "KexoBotClient"):
    """This function sets up the FunCommands cog."""
    await bot.add_cog(FunCommands(bot))
