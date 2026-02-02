import logging
import os
import re
import socket

from bson.objectid import ObjectId
from dotenv import load_dotenv

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
logging.getLogger("wavelink.node").setLevel(logging.CRITICAL)
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
DB_REDDIT_CACHE = {"_id": ObjectId("61795a8950149bebf7666e55")}
DB_SFD_ACTIVITY = {"_id": ObjectId("67eaab02440fd08b31d39a89")}
DB_CHOICES = {
    "Games": "games",
    "r/FreeGameFindings Exceptions": "freegamefindings_exceptions",
    "r/CrackWatch Exceptions": "crackwatch_exceptions",
    "Esutaze Exceptions": "esutaze_exceptions",
    "AlienwareArena Exceptions": "alienwarearena_exceptions",
}

############################# Discord Configuration ############################
CHANNEL_ID_KEXO_SERVER = 692810367851692032
CHANNEL_ID_SISKA_GANG_SERVER = 765262686908186654
CHANNEL_ID_DUCK_CULT = 484047204202446858
CHANNEL_ID_ESUTAZE_CHANNEL = 1302271245919981638
CHANNEL_ID_GAME_UPDATES_CHANNEL = 882185054174994462
CHANNEL_ID_FREE_STUFF_CHANNEL = 1081883673902714953
CHANNEL_ID_ALIENWARE_ARENA_NEWS_CHANNEL = 1368937624496115853

############################# User IDs ############################
USER_ID_KEXO = 402221830930432000

############################ Icons ############################
ICON_YOUTUBE = "https://freelogopng.com/images/all_img/1656501968youtube-icon-png.png"
ICON_DISCORD = (
    "https://img.icons8.com/?size=100&id=M725CLW4L7wE&format=png&color=000000"
)
ICON_REDDIT_FREEGAMEFINDINGS = (
    "https://styles.redditmedia.com/t5_30mv3/styles/communityIcon_xnoh6m7g9qh71.png"
)
ICON_REDDIT_CRACKWATCH = (
    "https://b.thumbs.redditmedia.com/zmVhOJSaEBYGMsE__QEZuBPSNM25gerc2hak9bQyePI.png"
)
ICON_REDDIT = "https://www.pngkit.com/png/full/207-2074270_reddit-icon-png.png"
ICON_GAME3RB = (
    "https://media.discordapp.net/attachments/796453724713123870"
    "/1162443171209433088/d95X3.png?ex=653bf491&is=65297f91&hm"
    "=c36058433d50580eeec7cd89ddfe60965ec297d6fc8054994fee5ae976bedfd3&="
)
ICON_ONLINEFIX = (
    "https://media.discordapp.net/attachments/"
    "796453724713123870/1035951759505506364/favicon-1.png"
)
ICON_ALIENWAREARENA = "https://www.pngarts.com/files/12/Alienware-PNG-Photo.png"
ICON_POWER_OUTAGES = (
    "https://www.hliniknadhronom.sk/portals_pictures/i_006868/i_6868718.png"
)
ICON_ESUTAZE = "https://www.esutaze.sk/wp-content/uploads/2014/07/esutaze-logo2.jpg"

############################# Reddit Configuration ############################
ENV_REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
ENV_REDDIT_SECRET = os.getenv("REDDIT_SECRET")
ENV_REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT")
ENV_REDDIT_USERNAME = os.getenv("REDDIT_USERNAME")
ENV_REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD")

REDDIT_TO_REMOVE = (" *", "* ", "*", "---")
REDDIT_FREEGAMEFINDINGS_MAX_RESULTS = 5
REDDIT_CRACKWATCH_MAX_RESULTS = 5

REDDIT_FREEGAMEFINDINGS_EMBEDS = {
    "Default": {
        "title": "",
        "description": "",
        "icon": "https://styles.redditmedia.com/t5_30mv3/styles/communityIcon_xnoh6m7g9qh71.png",
    },
    "Gleam": {
        "title": "Gleam",
        "description": "**Gleam** - keys from this site __disappear really fast__"
        " so you should get it fast!",
        "icon": "https://static-00.iconduck.com/assets.00/gleam-icon-512x512-vxvvbmg8.png",
    },
    "AlienwareArena": {
        "title": "AlienwareArena",
        "description": "**AlienwareArena** - "
        "keys from this site __disappear really fast__ so you should get it fast!",
        "icon": "https://play-lh.googleusercontent.com"
        "/X3K4HfYdxmascX5mRFikhuv8w8BYvg1Ny_R4ndNhF1C7GgjPeIKfROvbcOcjhafFmLdl",
    },
}

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

################ Fetchers / Game Deals Configuration ################

# Game3rb
SITE_URL_GAME3RB = "https://game3rb.com/category/games-online/"
GAME3RB_TO_REMOVE = (
    "Download ",
    " + OnLine",
    "-P2P",
    " Build",
    " + Update Only",
    " + Update",
    " + Online",
    " + 5 DLCs-FitGirl Repack",
    " Hotfix 1",
    ")-FitGirl Repack",
    " + Bonus Content DLC",
    " Hotfix 2 Hotfix",
    " rc",
    "\u200b",
    "-GOG",
    "-Repack",
    " VR",
    "/Denuvoless",
    " (Build",
    "-FitGirl Repack",
    "[Frankenpack]",
    "™",
    ")",
)

# Online-Fix
ONLINEFIX_MAX_RESULTS = 10
SITE_URL_ONLINEFIX = "https://online-fix.me/chat.php"

# AlienwareArena
ALIENWAREARENA_MAX_RESULTS = 3
SITE_URL_ALIENWAREARENA = (
    "https://eu.alienwarearena.com/esi/featured-tile-data/Giveaway"
)
ALIENWAREARENA_NEWS_URL = "https://eu.alienwarearena.com/relay/my-feed"
ALIENWAREARENA_TO_REMOVE = ("Key", "Giveaway", "Steam Game")

# Fanatical
FANATICAL_MAX_RESULTS = 3
API_FANATICAL = "https://www.fanatical.com/api/all-promotions/en"
API_FANATICAL_MEGAMENU = "https://www.fanatical.com/api/algolia/megamenu?altRank=false"
API_FANATICAL_IMG = "https://cdn-ext.fanatical.com/production/product/1280x720/"
FANATICAL_TO_REMOVE = (
    "Super Deluxe Edition",
    "Game of the Year Edition",
    "Platinum Edition",
    "Premium Edition",
    "Collector's Edition",
    "Game of the Year",
    "Deluxe Edition",
    "Gold Edition",
    "Ultimate Edition",
    "Complete Edition",
    "Definitive Edition",
    "Enhanced Edition",
    "Standard Edition",
    "Ultimate Edition",
    "Complete Edition",
    "Bundle Pack",
    "Bundle Collection",
    "Game Bundle",
    "Bundle",
)

# Power Outages
POWER_OUTAGES_MAX_RESULTS = 5
SITE_URL_POWER_OUTAGES = "https://www.hliniknadhronom.sk/get_rss.php?id=1_atom_1947"

# Esutaze
SITE_URL_ESUTAZE = "https://www.esutaze.sk/category/internetove-sutaze/feed/"

############################## SFD Configuration ############################
API_SFD_SERVER = "https://mythologicinteractive.com/SFDGameServices.asmx"
SFD_REQUEST = """<?xml version='1.0' encoding='utf-8'?>
    <soap12:Envelope xmlns:xsi='http://www.w3.org/2001/XMLSchema-instance'
     xmlns:xsd='http://www.w3.org/2001/XMLSchema' xmlns:soap12='http://www.w3.org/2003/05/soap-envelope'>
        <soap12:Body>
            <GetGameServers xmlns='https://mythologicinteractive.com/Games/SFD/'>
                <validationToken></validationToken>
            </GetGameServers>
        </soap12:Body>
    </soap12:Envelope>"""
SFD_HEADERS = {
    "Content-Type": "application/soap+xml; charset=utf-8",
    "SOAPAction": "https://mythologicinteractive.com/Games/SFD/GetGameServers",
}

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

############################## Joke APIs Configuration ############################
ENV_HUMOR_KEY = os.getenv("HUMOR_API_TOKENS").split(":")
API_JOKEAPI = "https://v2.jokeapi.dev/joke/Miscellaneous,Dark?amount=10"
API_HUMORAPI = "https://api.humorapi.com/jokes/search?number=10&include-tags="
API_DAD_JOKE = "https://icanhazdadjoke.com/search?limit=10"

JOKE_EXCLUDED_WORDS = [
    "muslim",
    "islam",
    "allah",
    "quran",
    "muhammad",
    "imam",
    "mosque",
    "ramadan",
    "eid",
    "sharia",
    "mecca",
    "hijab",
    "burqa",
    "jihad",
    "halal",
    "prophet",
    "religion",
    "faith",
    "prayer",
    "holy",
    "scripture",
    "divine",
    "jesus",
]

############################## Music / Radio Configuration ############################
# Lavalink
API_LAVALIST = "https://lavalink-list.ajieblogs.eu.org/All"
RAW_LAVALINK = (
    "https://raw.githubusercontent.com/botxlab/lavalink-list/refs/heads/main/nodes.json"
)

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

MUSIC_SUPPORTED_PLATFORMS = (
    "Youtube",
    "Youtube Music",
    "Soundcloud",
    "Spotify (likely)",
    "Apple Music (unlikely)",
    "Deezer (unlikely)",
    "Yandex Music (unlikely)",
    "VK Music (unlikely)",
    "Tidal (unlikely)",
    "Qobuz (unlikely)",
)

MUSIC_TO_REMOVE = (
    ";",
    "*",
    "https:",
    "http:",
    "/",
)

COUNTRIES = (
    "United States",
    "United Kingdom",
    "Germany",
    "France",
    "Russia",
    "China",
    "Japan",
    "India",
    "Brazil",
    "Australia",
    "Canada",
    "South Korea",
    "Italy",
    "Spain",
    "Mexico",
    "Turkey",
    "Egypt",
    "South Africa",
    "Argentina",
    "Indonesia",
    "Sweden",
    "Finland",
    "Hungary",
    "Slovakia",
    "Czech Republic",
)

############################# Wordnik API Configuration ############################
ENV_WORDNIK_KEY = os.getenv("WORDNIK_API_KEY")
API_WORDNIK = "https://api.wordnik.com/v4/words.json/wordOfTheDay?api_key="
