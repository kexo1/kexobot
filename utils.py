import aiohttp
import discord
import os


def load_text_file(name: str) -> list:
    with open(f"text_files/{name}.txt", encoding="utf8") as f:
        return f.read().split("\n")


def return_dict(subbredit_cache) -> dict:
    for key in subbredit_cache:
        search_level, nsfw, links, which_subreddit = subbredit_cache[key].split(",")
        subbredit_cache[key] = {"search_level": int(search_level), "nsfw": bool(nsfw), "links": links,
                                "which_subreddit": int(which_subreddit)}
    return subbredit_cache


class VideoDownloader:
    def __init__(self):
        self.session = None

    async def download_video(self, url, nsfw) -> discord.File:
        if not self.session:
            self.session = aiohttp.ClientSession()

            video_dir = os.path.join(os.getcwd(), "video")
            file_path = os.path.join(video_dir, "video.mp4")
            os.makedirs(video_dir, exist_ok=True)

        async with self.session.get(url) as response:
            with open(file_path, "wb") as f:
                try:
                    while True:
                        chunk = await response.content.read(1024)

                        if not chunk:
                            break

                        f.write(chunk)

                    if nsfw is True:
                        return discord.File(file_path, spoiler=True)
                    return discord.File(file_path)
                except Exception as e:
                    print(f"Failed to download video: \n{e}")
                    return None
