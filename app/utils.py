import os
from typing import Optional, Dict
from datetime import datetime

import discord
import aiohttp
import httpx
import psutil
import wavelink
import asyncio
import asyncpraw
import asyncpraw.models

from constants import SHITPOST_SUBREDDITS_DEFAULT, SONG_STRIP


def load_text_file(name: str) -> list:
    with open(f"text_files/{name}.txt", encoding="utf8") as f:
        return f.read().split("\n")


def iso_to_timestamp(iso_time: str) -> datetime:
    timestamp = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
    return timestamp


def get_file_age(file_path: str) -> float:
    if os.path.exists(file_path):
        file_time = os.path.getmtime(file_path)
        current_time = datetime.now().timestamp()
        return current_time - file_time
    return 0.0


def average(numbers: list) -> float:
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)


def get_memory_usage():
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    return mem_info.rss / (1024 * 1024)


async def download_video(
    session: httpx.AsyncClient, url: str, nsfw: bool
) -> Optional[discord.File]:
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
    return node


def strip_text(text: str, to_strip: tuple) -> str:
    for char in to_strip:
        text = text.replace(char, "")
    return text.strip()


def fix_audio_title(track: wavelink.Playable) -> str:
    if not track.title:
        title = track.uri
    else:
        title = track.title

    for char in SONG_STRIP:
        title = title.replace(char, "")
    return title.strip()


def is_older_than(hours: int, custom_datetime: datetime) -> bool:
    current_time = datetime.now()
    time_difference = current_time - custom_datetime
    return time_difference.total_seconds() > hours * 3600


def find_track(player: wavelink.Player, to_find: str) -> Optional[int]:
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


def generate_temp_guild_data() -> dict:
    return {"lavalink_server_pos": 0}


def generate_guild_data() -> dict:
    return {
        "autoplay_mode": wavelink.AutoPlayMode.partial,
        "volume": 100,
    }


async def generate_temp_user_data(
    reddit_agent: asyncpraw.Reddit, subreddits: list, user_id: int
) -> dict:
    multireddit: asyncpraw.models.Multireddit = await reddit_agent.multireddit(
        name=str(user_id), redditor="KexoBOT"
    )
    await multireddit.load()
    for subreddit in multireddit.subreddits:
        try:
            # For whatever reason, subbreddits are already added to the multireddit
            await multireddit.remove(subreddit)
        except asyncpraw.exceptions.RedditAPIException:
            pass

    for subreddit in subreddits:
        try:
            await multireddit.add(await reddit_agent.subreddit(subreddit))
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
    return {
        "reddit": {
            "subreddits": SHITPOST_SUBREDDITS_DEFAULT,
            "nsfw_posts": False,
        }
    }


async def get_selected_user_data(
    bot: discord.Bot, ctx: discord.ApplicationContext, selected_data: str
) -> tuple:
    user_id = ctx.author.id
    user_data: dict = bot.user_data.get(user_id)

    if user_data:
        if not bot.temp_user_data.get(user_id):
            # If temp user data is not present, generate it
            await ctx.defer()
            bot.temp_user_data[user_id] = await generate_temp_user_data(
                bot.reddit_agent, user_data["reddit"]["subreddits"], user_id
            )

        return user_data[selected_data], bot.temp_user_data[user_id][selected_data]

    await ctx.defer()

    user_data = await bot.user_data_db.find_one({"_id": user_id})  # Load from DB
    if user_data:
        bot.user_data.setdefault(user_id, {})[selected_data] = user_data[selected_data]
        temp_user_data = await generate_temp_user_data(
            bot.reddit_agent, user_data["reddit"]["subreddits"], user_id
        )
    else:  # If not in DB, create new user data
        user_data = generate_user_data()
        print("Creating new user data for user:", await bot.fetch_user(user_id))
        await bot.user_data_db.insert_one(
            {"_id": user_id, selected_data: user_data[selected_data]}
        )
        bot.user_data[user_id] = user_data

        temp_user_data = await generate_temp_user_data(
            bot.reddit_agent, SHITPOST_SUBREDDITS_DEFAULT, user_id
        )
    bot.temp_user_data[user_id] = temp_user_data
    return user_data[selected_data], temp_user_data[selected_data]


async def make_http_request(
    session: httpx.AsyncClient,
    url: str,
    headers: Optional[Dict] = None,
    retries: int = 1,
    timeout: float = 3.0,
) -> Optional[httpx.Response]:
    """
    Make an HTTP request with retry logic.

    Args:
        session: The httpx client session to use
        url: The URL to request
        headers: Optional headers to send with the request
        retries: Number of retry attempts
        timeout: Request timeout in seconds

    Returns:
        The response if successful, None if all retries failed
    """

    for attempt in range(retries):
        try:
            response = await session.get(url, headers=headers, timeout=timeout)
            # Don't raise for status for MP3 files as they might return 302 redirects
            if not url.endswith('.mp3'):
                response.raise_for_status()
            return response
        except (
            httpx.TimeoutException,
            httpx.ReadTimeout,
            httpx.ConnectError,
            httpx.HTTPError,
        ):
            if attempt == retries - 1:
                print('Failed to fetch URL after retries:', url)
                return None
            await asyncio.sleep(1 * (attempt + 1))
    return None
