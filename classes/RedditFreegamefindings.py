import discord

from urllib.parse import urlparse
from asyncprawcore.exceptions import AsyncPrawcoreException, ResponseException, RequestException

from constants import REDDIT_FREEGAME_EMBEDS, REDDIT_FREEGAME_MAX_POSTS, DB_CACHE, DB_LISTS


class RedditFreeGameFindings:
    def __init__(self, database, reddit, session, channel):
        self.database = database
        self.reddit = reddit
        self.session = session
        self.channel = channel
        self.upload = False

    async def run(self) -> None:
        freegamefindings_cache, to_filter = await self._load_database()
        freegamefindings_cache_upload = freegamefindings_cache

        subreddit = await self.reddit.subreddit("FreeGameFindings")

        try:
            async for submission in subreddit.new(limit=REDDIT_FREEGAME_MAX_POSTS):
                # If pinned, or is a thread
                if submission.is_self or submission.stickied:
                    continue

                if submission.url in freegamefindings_cache:
                    continue

                if "[PSA]" in submission.title and "Amazon" not in submission.title:
                    continue

                if "(Game)" not in submission.title:
                    continue

                if "https" not in submission.url:
                    continue

                is_filtered = [k for k in to_filter if k in submission.url]
                if is_filtered:
                    continue

                freegamefindings_cache_upload = [freegamefindings_cache_upload[-1]] + freegamefindings_cache_upload[:-1]
                freegamefindings_cache_upload[0] = submission.url
                await self._process_submission(submission.url)
        except (AsyncPrawcoreException, RequestException, ResponseException) as e:
            print(f"[FreeGameFindings] - Error while fetching subreddit:\n{e}")

        if self.upload:
            await self.database.update_one(DB_CACHE,
                                           {"$set": {"freegamefindings_cache": freegamefindings_cache_upload}})

    async def _process_submission(self, url: str) -> None:
        self.upload = True

        if "gleam" in url:
            await self._create_embed(REDDIT_FREEGAME_EMBEDS["Gleam"], url)
        elif "alienwarearena" in url:
            await self._alienwarearena(url)
        elif "fanatical" in url:
            await self._fanatical(url)
        else:
            await self._create_embed(REDDIT_FREEGAME_EMBEDS["Default"], url)

    async def _fanatical(self, url) -> None:
        await self.user_kexo.send(f"Update function!: {url}")
        return

    async def _alienwarearena(self, url) -> None:
        # There might be an occurence where giveaway is not showing in alienwarearena.com
        alienwarearena_cache = await self.database.find_one(DB_CACHE)
        reddit_path = url[29:]
        for cached_url in alienwarearena_cache["alienwarearena_cache"]:
            if reddit_path in cached_url:
                return
        await self._create_embed(REDDIT_FREEGAME_EMBEDS["AlienwareArena"], url)

    async def _create_embed(self, embed_dict: dict, url: str) -> None:
        url_obj = urlparse(url)
        domain = url_obj.netloc
        embed = discord.Embed(title=embed_dict["title"],
                              description=f"{embed_dict['description']}\n\n**[{domain}]({url})**",
                              color=discord.Color.dark_theme())
        embed.set_thumbnail(url=embed_dict["icon"])
        embed.set_footer(text="I took it from - r/FreeGameFindings",
                         icon_url="https://styles.redditmedia.com/t5_30mv3/styles/communityIcon_xnoh6m7g9qh71.png")
        await self.channel.send(embed=embed)

    async def _load_database(self) -> list:
        freegamefindings_cache = await self.database.find_one(DB_CACHE)
        to_filter = await self.database.find_one(DB_LISTS)
        return freegamefindings_cache["freegamefindings_cache"], to_filter["freegamefindings_exceptions"]
