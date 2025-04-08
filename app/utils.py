import os
from typing import Optional
from datetime import datetime

import discord
import httpx
import psutil


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
    response: httpx.Response = session.get(url)
    with open(video_path, "wb") as f:
        try:
            while True:
                chunk = await response.content.read(1024)

                if not chunk:
                    break

                f.write(chunk)

            if nsfw is True:
                return discord.File(video_path, spoiler=True)
            return discord.File(video_path)
        except httpx.ConnectError:
            print("Failed to download reddit video.")
            return None
