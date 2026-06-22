import logging
import os
import re
import socket
from enum import Enum

from bson.objectid import ObjectId
from discord import Color
from dotenv import load_dotenv
from fake_useragent import UserAgent

############################ Environment Variables ############################
LOCAL_MACHINE_NAME = "mato"
if LOCAL_MACHINE_NAME in socket.gethostname():
    load_dotenv(os.getenv("SECRET_PATH"))
    ENV_DISCORD_TOKEN = os.getenv("DISCORD_TOKEN_DEV")
else:
    ENV_DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

############################ Logging Configuration ############################
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)

formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(message)s", datefmt="%d/%m/%y %H:%M:%S"
)
console_handler.setFormatter(formatter)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

if logger.hasHandlers():
    logger.handlers.clear()

logger.addHandler(console_handler)

logging.getLogger("aiohttp").setLevel(logging.CRITICAL)
logging.getLogger("aiohttp.client").setLevel(logging.CRITICAL)
logging.getLogger("sonolink").setLevel(logging.CRITICAL)
"""
logging.getLogger("sonolink.node").setLevel(logging.CRITICAL)
logging.getLogger("sonolink.client").setLevel(logging.CRITICAL)
logging.getLogger("sonolink.websocket").setLevel(logging.CRITICAL)
logging.getLogger("sonolink.player").setLevel(logging.CRITICAL) """
logging.getLogger("discord.client").setLevel(logging.WARNING)
logging.getLogger("discord.gateway").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

############################ MongoDB Configuration ############################
ENV_API_DB = (
    f"mongodb+srv://{os.getenv('MONGO_KEY')}"
    f"@cluster0.exygx.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
)

DB_CACHE = {"_id": ObjectId("617958fae4043ee4a3f073f2")}
DB_LISTS = {"_id": ObjectId("6178211ec5f5c08c699b8fd3")}
DB_SFD_ACTIVITY = {"_id": ObjectId("67eaab02440fd08b31d39a89")}
DB_CHOICES = {
    "Games": "games",
    "r/FreeGameFindings Exceptions": "freegamefindings_exceptions",
    "r/CrackWatch Exceptions": "crackwatch_exceptions",
    "AlienwareArena Exceptions": "alienwarearena_exceptions",
}

############################# Discord Configuration ############################
CHANNEL_ID_KEXO_SERVER = 692810367851692032
CHANNEL_ID_GAME_UPDATES_CHANNEL = 882185054174994462
CHANNEL_ID_GAME_CRACKS_CHANNEL = 1468585889574813903
CHANNEL_ID_FREE_STUFF_CHANNEL = 1081883673902714953

############################# User Agent Configuration ############################
try:
    USER_AGENT = UserAgent(min_version=120.0).random
except Exception:
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"


############################ Icons ############################
ICON_YOUTUBE = "https://freelogopng.com/images/all_img/1656501968youtube-icon-png.png"
ICON_DISCORD = (
    "https://img.icons8.com/?size=100&id=M725CLW4L7wE&format=png&color=000000"
)
ICON_REDDIT = "https://www.pngkit.com/png/full/207-2074270_reddit-icon-png.png"

############################# Reddit Configuration ############################
ENV_REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
ENV_REDDIT_SECRET = os.getenv("REDDIT_SECRET")
ENV_REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT")
ENV_REDDIT_USERNAME = os.getenv("REDDIT_USERNAME")
ENV_REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD")

SHITPOST_SUBREDDITS_DEFAULT = (
    "discordVideos",
    "okbuddyretard",
    "shitposting",
    "MemeVideos",
    "doodoofard",
)

SHITPOST_SUBREDDITS_ALL = (
    "discordVideos",
    "okbuddyretard",
    "MemeVideos",
    "doodoofard",
    "dankvideos",
    "whenthe",
    "ihaveihaveihavereddit",
    "memes",
    "simpsonsshitposting",
    "shitposting",
    "clamworks",
)

############################## Joke APIs Configuration ############################
_humor_api_tokens = os.getenv("HUMOR_API_TOKENS", "")
ENV_HUMOR_KEY = [token for token in _humor_api_tokens.split(":") if token]

############################## SFD Configuration ############################
TIMEZONES = {
    "New_York": "America/New_York",
    "London": "Europe/London",
    "Tokyo": "Asia/Tokyo",
    "Shanghai": "Asia/Shanghai",
    "Slovakia": "Europe/Bratislava",
    "Russia": "Europe/Moscow",
    "Spain": "Europe/Madrid",
    "Italy": "Europe/Rome",
}
SFD_TIMEZONE_CHOICE = list(TIMEZONES.keys())

############################## Music / Radio Configuration ############################
# Radiogarden
API_RADIOGARDEN_PLACES = "https://radio.garden/api/ara/content/places"
API_RADIOGARDEN_PAGE = "https://radio.garden/api/ara/content/page/"
API_RADIOGARDEN_SEARCH = "https://radio.garden/api/search?q="
API_RADIOGARDEN_LISTEN = "https://radio.garden/api/ara/content/listen/"

# Music Sources
MUSIC_SOURCES = [
    # YouTube Music (music.youtube.com URLs)
    (
        re.compile(
            r"""(?ix)
            https?://music\.youtube\.com/
            (?:watch\?v=|playlist\?list=|channel/|@|user/)
            """
        ),
        "ytmsearch",
    ),
    # YouTube (youtube.com, youtu.be URLs)
    (
        re.compile(
            r"""(?ix)
            https?://(?:www\.)?(?:youtube\.com|youtu\.be)/
            (?:
                watch\?v=|
                playlist\?list=|
                embed/|
                v/|
                shorts/|
                live/|
                channel/|
                @|
                user/|
                attribution_link\?.*v=
            )
            """
        ),
        "ytsearch",
    ),
    # Spotify (prefer ytsearch over spsearch)
    (
        re.compile(
            r"""(?ix)
            https?://open\.spotify\.com/
            (?:intl-[\w-]+/)?
            (?:track|album|playlist|artist)/\w+
            """
        ),
        "spsearch",
    ),
    # Apple Music
    (
        re.compile(
            r"""(?ix)
            https?://music\.apple\.com/
            [\w-]+/(?:album|playlist|artist)/[\w-]+
            """
        ),
        "amsearch",
    ),
    # Deezer
    (
        re.compile(
            r"""(?ix)
            https?://(?:www\.)?deezer\.com/
            (?:track|album|playlist|artist)/\d+|
            https?://deezer\.page\.link/\w+
            """
        ),
        "dzsearch",
    ),
    # Yandex Music
    (
        re.compile(
            r"""(?ix)
            https?://music\.yandex\.ru/
            (?:album/\d+(?:/track/\d+)?|
            track/\d+|
            users/[^/]+/playlists/\d+|
            artist/\d+)
            """
        ),
        "ymsearch",
    ),
    # VK Music
    (
        re.compile(
            r"""(?ix)
            https?://(?:vk\.com|vk\.ru)/
            (?:audio|audios|music/playlist|music/album|artist)/\S+
            """
        ),
        "vksearch",
    ),
    # Tidal
    (
        re.compile(
            r"""(?ix)
            https?://tidal\.com/browse/
            (?:track|album|playlist|artist)/\d+
            """
        ),
        "tdsearch",
    ),
    # Qobuz
    (
        re.compile(
            r"""(?ix)
            https?://(?:open|play)\.qobuz\.com/
            (?:track|album|playlist|artist)/\w+|
            https?://www\.qobuz\.com/[\w-]+/album/[\w-]+
            """
        ),
        "qbsearch",
    ),
]


class AudioSourceSupport(Enum):
    LIKELY = "likely"
    UNLIKELY = "unlikely"


PLUGIN_PLATFORM_REGISTRY: dict[str, dict[str, AudioSourceSupport]] = {
    "youtube": {
        "YouTube": AudioSourceSupport.LIKELY,
        "YouTube Music": AudioSourceSupport.LIKELY,
    },
    "yt-": {
        "YouTube": AudioSourceSupport.LIKELY,
        "YouTube Music": AudioSourceSupport.LIKELY,
    },
    "lavasrc": {
        "Spotify": AudioSourceSupport.LIKELY,
        "Apple Music": AudioSourceSupport.UNLIKELY,
        "Deezer": AudioSourceSupport.UNLIKELY,
        "Yandex Music": AudioSourceSupport.UNLIKELY,
        "YouTube": AudioSourceSupport.UNLIKELY,
        "YouTube Music": AudioSourceSupport.UNLIKELY,
        "VK Music": AudioSourceSupport.UNLIKELY,
        "Tidal": AudioSourceSupport.UNLIKELY,
        "Qobuz": AudioSourceSupport.UNLIKELY,
    },
    "lavasearch": {
        "Spotify": AudioSourceSupport.LIKELY,
        "Apple Music": AudioSourceSupport.UNLIKELY,
        "Deezer": AudioSourceSupport.UNLIKELY,
        "Yandex Music": AudioSourceSupport.UNLIKELY,
        "YouTube": AudioSourceSupport.UNLIKELY,
        "YouTube Music": AudioSourceSupport.UNLIKELY,
        "VK Music": AudioSourceSupport.UNLIKELY,
        "Tidal": AudioSourceSupport.UNLIKELY,
        "Qobuz": AudioSourceSupport.UNLIKELY,
    },
    "slugyzeon": {
        "Spotify": AudioSourceSupport.LIKELY,
        "YouTube": AudioSourceSupport.LIKELY,
        "Amazon Music": AudioSourceSupport.UNLIKELY,
        "Gaana": AudioSourceSupport.UNLIKELY,
    },
    "amazonmusic": {
        "Amazon Music": AudioSourceSupport.LIKELY,
    },
    "amazon-music": {
        "Amazon Music": AudioSourceSupport.LIKELY,
    },
}

PLATFORM_EMOJIS: dict[str, str] = {
    "Spotify": "🟢",
    "YouTube": "🔴",
    "YouTube Music": "🎵",
    "Apple Music": "🍎",
    "Deezer": "🟣",
    "Yandex Music": "🟡",
    "VK Music": "🔵",
    "Tidal": "🌊",
    "Qobuz": "🎼",
    "Amazon Music": "📦",
    "Gaana": "🎶",
}

MUSIC_TO_REMOVE = (
    ";",
    "*",
    "https:",
    "http:",
    "/",
)

############################# Wordnik API Configuration ############################
ENV_WORDNIK_KEY = os.getenv("WORDNIK_API_KEY")
API_WORDNIK = "https://api.wordnik.com/v4/words.json/wordOfTheDay?api_key="

############################# Shared Embed Colors ############################
COLOR_BLUE = Color.blue()
COLOR_RED = Color.from_rgb(r=220, g=0, b=0)
COLOR_RED_DARK = Color.from_rgb(r=200, g=0, b=0)
COLOR_GREEN = Color.green()
COLOR_GREEN_SUCCESS = Color.from_rgb(r=0, g=200, b=0)
COLOR_YELLOW = Color.yellow()
COLOR_ORANGE = Color.orange()
COLOR_ORANGE_LIGHT = Color.from_rgb(r=220, g=165, b=0)
COLOR_GOLD = Color.gold()
