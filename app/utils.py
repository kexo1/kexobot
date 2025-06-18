import asyncio
import json
import os
from datetime import datetime
from typing import Optional, Dict, Callable, Any

import aiohttp
import asyncpraw
import asyncpraw.models
import asyncprawcore
import discord
import httpx
import psutil
import wavelink

from app.constants import (
    SHITPOST_SUBREDDITS_DEFAULT,
    SONG_STRIP,
    SOURCE_PATTERNS,
    DISCORD_ICON,
)


def load_text_file(name: str) -> list:
    """This function loads a text file and returns its content as a list of strings.

    Parameters
    ----------
    name: str
        The name of the text file to load (without the .txt extension).
    """
    with open(f"text_files/{name}.txt", encoding="utf8") as f:
        return f.read().split("\n")


def iso_to_timestamp(iso_time: str) -> datetime:
    """Convert an ISO 8601 formatted string to a datetime object.

    Parameters
    ----------
    iso_time: str
        The ISO 8601 formatted string to convert.

    Returns
    -------
    :class:`datetime.datetime`
        The converted datetime object.
    """
    timestamp = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
    return timestamp


def get_file_age(file_path: str) -> float:
    """Get the age of a file in seconds.

    Parameters
    ----------
    file_path: str
        The path to the file.

    Returns
    -------
    float
        The age of the file in seconds.
    """
    if os.path.exists(file_path):
        file_time = os.path.getmtime(file_path)
        current_time = datetime.now().timestamp()
        return current_time - file_time
    return 0.0


def average(numbers: list) -> float:
    """Calculate the average of a list of numbers.

    Parameters
    ----------
    numbers: list
        The list of numbers to calculate the average of.

    Returns
    -------
    float
        The average of the numbers in the list.
    """
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)


def get_memory_usage():
    """Get the current memory usage of the process in MB.

    Returns
    -------
    float
        The current memory usage of the process in MB.
    """
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    return mem_info.rss / (1024 * 1024)


async def download_video(
    session: httpx.AsyncClient, url: str, nsfw: bool
) -> Optional[discord.File]:
    """Download a video from a given URL and return it as a discord.File.

    Parameters
    ----------
    session: :class:`httpx.AsyncClient`
        The httpx client session to use for the request.
    url: str
        The URL of the video to download.
    nsfw: bool
        Whether the video is NSFW (not safe for work).

    Returns
    -------
    :class:`discord.File`
        The downloaded video as a discord.File.
    """
    video_folder = os.path.join(os.getcwd(), "video")
    os.makedirs(video_folder, exist_ok=True)
    video_path = os.path.join(video_folder, "video.mp4")

    try:
        async with session.stream("GET", url) as response:
            with open(video_path, "wb") as f:
                async for chunk in response.aiter_bytes(1024):
                    f.write(chunk)
        if nsfw:
            return discord.File(video_path, spoiler=True)
        return discord.File(video_path)

    except httpx.ReadTimeout:
        print("Request timed out while downloading the video.")
        return None
    except httpx.ConnectError:
        print("Failed to connect to the server.")
        return None


async def check_node_status(
    bot: discord.Bot, uri: str, password: str
) -> Optional[wavelink.Node]:
    """Check the status of a Lavalink node and return it if it's online.

    Parameters
    ----------
    bot: :class:`discord.Bot`
        The discord bot instance.
    uri: str
        The URI of the Lavalink node to check.
    password: str
        The password for the Lavalink node.

    Returns
    -------
    :class:`wavelink.Node`
        The Lavalink node if it's online, None otherwise.
    """
    node = [
        wavelink.Node(
            uri=uri,
            password=password,
            retries=1,
            resume_timeout=0,
        )
    ]
    try:
        await asyncio.wait_for(wavelink.Pool.connect(nodes=node, client=bot), timeout=3)
        await node[0].fetch_info()
    except (
        asyncio.TimeoutError,
        wavelink.exceptions.NodeException,
        wavelink.LavalinkException,
        aiohttp.NonHttpUrlClientError,
    ):
        return None
    return node[0]


def strip_text(text: str, to_strip: tuple) -> str:
    """Strip unwanted characters from a string.

    Parameters
    ----------
    text: str
        The string to strip.
    to_strip: tuple
        The characters to strip from the string.

    Returns
    -------
    str
        The stripped string.
    """
    for char in to_strip:
        text = text.replace(char, "")
    return text.strip()


def fix_audio_title(track: wavelink.Playable) -> str:
    """Fix the title of an audio track by removing unwanted characters.

    Parameters
    ----------
    track: :class:`wavelink.Playable`
        The audio track to fix.

    Returns
    -------
    str
        The fixed title of the audio track.
    """
    if track.title and track.title != "Unknown title":
        title = track.title
    else:
        title = track.uri

    for char in SONG_STRIP:
        title = title.replace(char, "")
    return title.strip()


def is_older_than(hours: int, custom_datetime: datetime) -> bool:
    """Check if a given datetime is older than a specified number of hours.

    Parameters
    ----------
    hours: int
        The number of hours to check against.
    custom_datetime: :class:`datetime.datetime`
        The datetime to check.

    Returns
    -------
    bool
        True if the datetime is older than the specified number of hours, False otherwise.
    """
    current_time = datetime.now()

    if custom_datetime.tzinfo is not None and current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=custom_datetime.tzinfo)
    time_difference = current_time - custom_datetime
    return time_difference.total_seconds() > hours * 3600


def get_search_prefix(query: str) -> Optional[str]:
    """Get the search prefix for a given query.

    Parameters
    ----------
    query: str
        The query to check.

    Returns
    -------
    str | None
        The search prefix if found, None otherwise.
    """
    for pattern, prefix in SOURCE_PATTERNS:
        if pattern.search(query):
            return prefix
    return None


def find_track(player: wavelink.Player, to_find: str) -> Optional[int]:
    """Find a track in the player's queue by title or index.

    Parameters
    ----------
    player: :class:`wavelink.Player`
        The wavelink Player instance.
    to_find: str
        The title or index of the track to find.

    Returns
    -------
    int | None
        The index of the track in the queue if found, None otherwise.
    """
    if not to_find.isdigit():
        for i, track in enumerate(player.queue):
            if to_find.lower() in track.title.lower():
                to_find = i + 1
                break

            if i != len(player.queue) - 1:
                continue

            return None
    else:
        to_find = int(to_find)
        if to_find > len(player.queue):
            return None

    return to_find


def has_pfp(member: discord.Member) -> str:
    """Check if a member has a profile picture and return its URL.

    If not, return a default discord icon URL.

    Parameters
    ----------
    member: :class:`discord.Member`
        The member to check.

    Returns
    -------
    str
        The URL of the member's profile picture or a default icon.
    """
    if hasattr(member.avatar, "url"):
        return member.display_avatar.url
    return DISCORD_ICON


# I don't know if passing callable is the best way to do this, yet since connect_node is a
# method of KexoBot, I don't see another way to do it
async def switch_node(
    connect_node: Callable[[], wavelink.Node],
    player: wavelink.Player,
    play_after: bool = True,
    offline_node: str = None,
) -> Optional[wavelink.Node]:
    """
    Attempt to switch to a new node for audio playback.

    Parameters:
    ----------
    connect_node: Callable[[], wavelink.Node]
        A callable that returns a new wavelink.Node instance.
    player: :class:`wavelink.Player`
        The wavelink Player instance to switch the node for.
    play_after: bool
        Whether to play the current track after switching nodes.

    Returns
    -------
    :class:`wavelink.Node` | None
        The new wavelink.Node instance if successful, None otherwise.
    """
    for i in range(5):
        try:
            player_autoplay_mode = player.autoplay
            player.autoplay = wavelink.AutoPlayMode.disabled

            node: wavelink.Node = await connect_node(player.guild.id, offline_node)
            await player.switch_node(node)

            # When populated queue is on, the player can put random song and skip currently playing song
            if not play_after and player_autoplay_mode == wavelink.AutoPlayMode.enabled:
                try:
                    del player.queue[0]
                except IndexError:
                    pass

            if play_after:
                await player.play(player.temp_current)

            player.autoplay = player_autoplay_mode
            print(f"{i + 1}. Node switched. ({node.uri})")
            embed = discord.Embed(
                title="",
                description=f"**:white_check_mark: Successfully connected to `{node.uri}`**",
                color=discord.Color.green(),
            )
            await player.text_channel.send(embed=embed)
            return node
        except (
            wavelink.LavalinkException,
            wavelink.InvalidNodeException,
            RuntimeError,
        ):
            pass

    embed = discord.Embed(
        title="",
        description=":x: Failed to connect to a new node, try `/reconnect_node`",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    )
    await player.text_channel.send(embed=embed)
    return None


def generate_temp_guild_data() -> dict:
    """Generate temporary guild data for the bot.

    Returns
    -------
    dict
        A dictionary containing temporary guild data.
    """
    return {
        "lavalink_server_pos": 0,
        "jokes": {
            "viewed_jokes": [],
            "viewed_dad_jokes": [],
            "viewed_yo_mama_jokes": [],
        },
    }


def generate_guild_data() -> dict:
    """Generate default guild data for the bot.

    Returns
    -------
    dict
        A dictionary containing default guild data.
    """
    return {
        "music": {
            "autoplay_mode": 1,
            "volume": 100,
        },
    }


async def generate_temp_user_data(bot: discord.Bot, user_id: int) -> dict:
    """Generate temporary user data for the bot.

    Parameters
    ----------
    bot: :class:`discord.Bot`
        The discord bot instance.
    user_id: int
        The ID of the user to generate temporary data for.

    Returns
    -------
    dict
        A dictionary containing temporary user data.
    """
    multireddit: asyncpraw.models.Multireddit = await bot.reddit_agent.multireddit(
        name=str(user_id), redditor="KexoBOT"
    )
    for attempt in range(3):
        try:
            await multireddit.load()
            break
        except asyncprawcore.exceptions.NotFound:
            await asyncio.sleep(attempt + 1)

    for subreddit in multireddit.subreddits:
        try:
            # For whatever reason, subbreddits are already added to the multireddit
            await multireddit.remove(subreddit)
        except asyncpraw.exceptions.RedditAPIException:
            pass

    for subreddit in bot.user_data[user_id]["reddit"]["subreddits"]:
        try:
            await multireddit.add(await bot.reddit_agent.subreddit(subreddit))
        except asyncpraw.exceptions.RedditAPIException:
            pass
    return {
        "reddit": {
            "viewed_posts": set(),
            "search_limit": 3,
            "last_used": datetime.now(),
            "multireddit": multireddit,
        }
    }


def generate_user_data() -> dict:
    """Generate default user data for the bot.

    Returns
    -------
    dict
        A dictionary containing default user data.
    """
    return {
        "reddit": {
            "subreddits": SHITPOST_SUBREDDITS_DEFAULT,
            "nsfw_posts": False,
        }
    }


def fix_user_data(old_data: dict) -> dict:
    """Fixes user data by adding missing keys and values.

    Parameters
    ----------
    old_data: dict
        The old data to be fixed.

    Returns
    -------
    dict
        The fixed data with all required keys and values.
    """
    data = old_data.copy()
    return fix_data(data, generate_user_data)


def fix_guild_data(old_data: dict) -> dict:
    """Fixes guild data by adding missing keys and values.

    Parameters
    ----------
    old_data: dict
        The old data to be fixed.

    Returns
    -------
    dict
        The fixed data with all required keys and values.
    """
    data = old_data.copy()
    return fix_data(data, generate_guild_data)


def fix_data(
    fixed_data: Dict[str, Any], generator: Callable[[], Dict[str, Any]]
) -> Dict[str, Any]:
    """Generic function to fix data by adding missing keys and values from a generator.

    Parameters
    ----------
    fixed_data: dict
        The data to be fixed.
    generator: Callable[[], dict]
        A callable that generates the default data structure.

    Returns
    -------
    dict
        The fixed data with all required keys and values.
    """
    default_data = generator()

    for key, value in default_data.items():
        if key not in fixed_data:
            fixed_data[key] = value
        elif isinstance(value, dict):
            for sub_key, sub_value in value.items():
                if sub_key not in fixed_data[key]:
                    fixed_data[key][sub_key] = sub_value

    return fixed_data


async def get_user_data(bot: discord.Bot, ctx: discord.ApplicationContext) -> tuple:
    """Get user data for the given user.

    Parameters
    ----------
    bot: :class:`discord.Bot`
        The discord bot instance.
    ctx: :class:`discord.ApplicationContext`
        The context of the command invocation.

    Returns
    -------
    tuple
        A tuple containing the user data and temporary user data.
    """
    user_id = ctx.author.id
    user_data: dict = bot.user_data.get(user_id)

    if user_data:
        return user_data, bot.temp_user_data[user_id]

    await ctx.defer()

    user_data = await bot.user_data_db.find_one({"_id": user_id})  # Load from DB
    if user_data:
        fixed_data = fix_user_data(user_data)
        bot.user_data[user_id] = fixed_data
        temp_user_data = await generate_temp_user_data(bot, user_id)
    else:  # If not in DB, create new user data
        user_data = generate_user_data()
        print("Creating new user data for user:", await bot.fetch_user(user_id))
        await bot.user_data_db.insert_one({"_id": user_id, **user_data})
        bot.user_data[user_id] = user_data

        temp_user_data = await generate_temp_user_data(bot, user_id)
    bot.temp_user_data[user_id] = temp_user_data
    return user_data, temp_user_data


async def get_guild_data(bot: discord.Bot, guild_id: int) -> tuple:
    """Get guild data for the given guild.

    Parameters
    ----------
    bot: :class:`discord.Bot`
        The discord bot instance.
    guild_id: int
        The ID of the guild to get data for.

    Returns
    -------
    tuple
        A tuple containing the guild data and temporary guild data.
    """
    guild_data: dict = bot.guild_data.get(guild_id)

    if guild_data:
        return guild_data, bot.temp_guild_data[guild_id]

    guild_data = await bot.guild_data_db.find_one({"_id": guild_id})  # Load from DB
    if guild_data:
        fixed_data = fix_guild_data(guild_data)
        bot.guild_data[guild_id] = fixed_data
        temp_guild_data = generate_temp_guild_data()
    else:  # If not in DB, create new guild data
        guild_data = generate_guild_data()
        guild_name = await bot.fetch_guild(guild_id)
        print("Creating new guild data for server:", guild_name)
        await bot.guild_data_db.insert_one({"_id": guild_id, **guild_data})
        bot.guild_data[guild_id] = guild_data
        temp_guild_data = generate_temp_guild_data()

    bot.temp_guild_data[guild_id] = temp_guild_data
    return guild_data, temp_guild_data


async def make_http_request(
    session: httpx.AsyncClient,
    url: str,
    data: Optional[Dict] = None,
    headers: Optional[Dict] = None,
    retries: int = 2,
    timeout: float = 3.0,
    get_json: bool = False,
    binary: bool = False,
) -> Optional[httpx.Response]:
    """
    Make an HTTP request with retry logic.

    Parameters
    ----------
    session: :class:`httpx.AsyncClient`
        The httpx client session to use for the request.
    url: str
        The URL to make the request to.
    data: dict | None
        The data to send with the request (for POST requests).
    headers: dict | None
        The headers to include with the request.
    retries: int
        The number of times to retry the request on failure.
    timeout: float
        The timeout for the request in seconds.
    get_json: bool
        Whether to return the response as JSON.
    binary: bool
        Whether to treat the response as binary content (e.g., MP3 files).

    Returns
    -------
    :class:`httpx.Response` | None
        The response from the request, or None if the request failed.
    """
    for attempt in range(retries):
        try:
            if data:
                response = await session.post(
                    url, data=data, headers=headers, timeout=timeout
                )
            else:
                response = await session.get(url, headers=headers, timeout=timeout)

            # Don't raise for status for MP3 files or binary content
            if not (url.endswith(".mp3") or binary):
                response.raise_for_status()

            if get_json:
                return response.json()
            return response
        except (
            httpx.ReadTimeout,
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.HTTPError,
        ) as e:
            if attempt == retries - 1:
                print(f"Request failed ({type(e).__name__}): ", url)
                return None
            await asyncio.sleep(1 * (attempt + 1))
        except json.decoder.JSONDecodeError:
            print("Failed to decode JSON: ", url)
    return None


# noinspection PyUnusedLocal
class QueuePaginator(discord.ui.View):
    """A paginator for the queue command.

    This class creates a view with two buttons, "Previous" and Next",
    that allow the user to navigate through the pages of the queue."

    Parameters
    ----------
    embeds : list
        A list of embeds to be displayed in the paginator.
    timeout : int
        The time in seconds before the paginator times out. Default is 600 seconds.
    """

    def __init__(self, embeds: list, timeout: int = 600) -> None:
        super().__init__(timeout=timeout)
        self._embeds = embeds
        self._current_page = 0

    async def update_message(self, interaction: discord.Interaction) -> None:
        """Updates the message with the current embed.

        Parameters
        ----------
        interaction: :class:`discord.Interaction`
            The interaction that triggered the button click.
        """
        await interaction.response.edit_message(
            embed=self._embeds[self._current_page], view=self
        )

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.blurple)
    async def previous(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        """Handles the "Previous" button click event.

        Parameters
        ----------
        button: :class:`discord.ui.Button`
            The button that was clicked.
        interaction: :class:`discord.Interaction`
            The interaction that triggered the button click.
        """
        if self._current_page > 0:
            self._current_page -= 1
        else:
            self._current_page = len(self._embeds) - 1
        await self.update_message(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.blurple)
    async def next(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        """Handles the "Next" button click event.

        Parameters
        ----------
        button: :class:`discord.ui.Button`
            The button that was clicked.
        interaction: :class:`discord.Interaction`
            The interaction that triggered the button click.
        """
        if self._current_page < len(self._embeds) - 1:
            self._current_page += 1
        else:
            self._current_page = 0
        await self.update_message(interaction)
