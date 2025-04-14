import os
from typing import Optional
from datetime import datetime

import discord
import httpx
import psutil
import wavelink
import asyncio


def load_text_file(name: str) -> list:
    with open(f"text_files/{name}.txt", encoding="utf8") as f:
        return f.read().split("\n")


def return_dict(subbredit_cache) -> dict:
    for key in subbredit_cache:
        search_level, nsfw, urls, which_subreddit = subbredit_cache[key].split(",")
        subbredit_cache[key] = {
            "search_level": int(search_level),
            "nsfw": bool(nsfw),
            "urls": urls,
            "which_subreddit": int(which_subreddit),
        }
    return subbredit_cache


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


async def check_node_status(uri: str, password: str) -> Optional[wavelink.Node]:
    node = [
        wavelink.Node(
            uri=uri,
            password=password,
            retries=1,
            resume_timeout=0,
        )
    ]
    try:
        await asyncio.wait_for(
            wavelink.Pool.connect(nodes=node, client=self.bot), timeout=3
        )
        await node[0].fetch_info()
    except (asyncio.TimeoutError, wavelink.exceptions.NodeException):
        return None
    return node


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
