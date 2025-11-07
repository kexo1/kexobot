import logging
import os
import re
import socket

from bson.objectid import ObjectId
from dotenv import load_dotenv

# -------------------- Logging Configuration -------------------- #
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
logging.getLogger("wavelink.node").setLevel(logging.ERROR)
logging.getLogger("wavelink.player").setLevel(logging.ERROR)
logging.getLogger("discord.client").setLevel(logging.WARNING)
logging.getLogger("discord.gateway").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# -------------------- Environment Configuration -------------------- #
LOCAL_MACHINE_NAME = "mato"
if LOCAL_MACHINE_NAME in socket.gethostname():
    load_dotenv(os.getenv("SECRET_PATH"))
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN_DEV")
else:
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# -------------------- Discord Channel IDs -------------------- #
KEXO_SERVER = 692810367851692032
SISKA_GANG_SERVER = 765262686908186654
DUCK_CULT = 484047204202446858
ESUTAZE_CHANNEL = 1302271245919981638
GAME_UPDATES_CHANNEL = 882185054174994462
FREE_STUFF_CHANNEL = 1081883673902714953
ALIENWARE_ARENA_NEWS_CHANNEL = 1368937624496115853
# -------------------- User IDs -------------------- #
USER_KEXO = 402221830930432000

# -------------------- Icons -------------------- #
YOUTUBE_ICON = "https://freelogopng.com/images/all_img/1656501968youtube-icon-png.png"
DISCORD_ICON = (
    "https://img.icons8.com/?size=100&id=M725CLW4L7wE&format=png&color=000000"
)
REDDIT_FREEGAME_ICON = (
    "https://styles.redditmedia.com/t5_30mv3/styles/communityIcon_xnoh6m7g9qh71.png"
)
REDDIT_CRACKWATCH_ICON = (
    "https://b.thumbs.redditmedia.com/zmVhOJSaEBYGMsE__QEZuBPSNM25gerc2hak9bQyePI.png"
)
REDDIT_ICON = "https://www.pngkit.com/png/full/207-2074270_reddit-icon-png.png"
GAME3RB_ICON = (
    "https://media.discordapp.net/attachments/796453724713123870"
    "/1162443171209433088/d95X3.png?ex=653bf491&is=65297f91&hm"
    "=c36058433d50580eeec7cd89ddfe60965ec297d6fc8054994fee5ae976bedfd3&="
)
ONLINEFIX_ICON = (
    "https://media.discordapp.net/attachments/"
    "796453724713123870/1035951759505506364/favicon-1.png"
)
ALIENWAREARENA_ICON = "https://www.pngarts.com/files/12/Alienware-PNG-Photo.png"
POWER_OUTAGES_ICON = (
    "https://www.hliniknadhronom.sk/portals_pictures/i_006868/i_6868718.png"
)
ESUTAZE_ICON = "https://www.esutaze.sk/wp-content/uploads/2014/07/esutaze-logo2.jpg"

# -------------------- MongoDB Configuration -------------------- #
MONGO_DB_URL = (
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

# -------------------- Reddit Configuration -------------------- #
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_SECRET = os.getenv("REDDIT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT")
REDDIT_USERNAME = os.getenv("REDDIT_USERNAME")
REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD")
REDDIT_STRIP = (" *", "* ", "*", "---")
REDDIT_FREEGAME_MAX_POSTS = 5
REDDIT_CRACKWATCH_POSTS = 5


REDDIT_FREEGAME_EMBEDS = {
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

# -------------------- Game3rb Configuration -------------------- #
GAME3RB_URL = "https://game3rb.com/category/games-online/"
GAME3RB_STRIP = (
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

# -------------------- Online-Fix Configuration -------------------- #
ONLINEFIX_MAX_GAMES = 10
ONLINEFIX_URL = "https://online-fix.me/chat.php"

# -------------------- AlienwareArena Configuration -------------------- #
ALIENWAREARENA_MAX_POSTS = 3
ALIENWAREARENA_URL = "https://eu.alienwarearena.com/esi/featured-tile-data/Giveaway"
ALIENWAREARENA_NEWS_URL = "https://eu.alienwarearena.com/relay/my-feed"
ALIENWAREARENA_STRIP = ("Key", "Giveaway", "Steam Game")

# -------------------- Fanatical Configuration -------------------- #
FANATICAL_MAX_POSTS = 3
FANATICAL_API_URL = "https://www.fanatical.com/api/all-promotions/en"
FANATICAL_API_MEGAMENU_URL = (
    "https://www.fanatical.com/api/algolia/megamenu?altRank=false"
)
FANATICAL_IMG_URL = "https://cdn-ext.fanatical.com/production/product/1280x720/"
FANATICAL_STRIP = (
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

# -------------------- Power Outages Configuration -------------------- #
POWER_OUTAGES_MAX_ARTICLES = 5
POWER_OUTAGES_URL = "https://www.hliniknadhronom.sk/get_rss.php?id=1_atom_1947"

# -------------------- Esutaze Configuration -------------------- #
ESUTAZE_URL = "https://www.esutaze.sk/category/internetove-sutaze/feed/"

# -------------------- SFD Game Configuration -------------------- #
SFD_SERVER_URL = "https://mythologicinteractive.com/SFDGameServices.asmx"
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

# -------------------- Timezone Configuration -------------------- #
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

# -------------------- Fun Stuff Configuration -------------------- #
HUMOR_API_SECRET = os.getenv("HUMOR_API_TOKENS").split(":")
JOKE_API_URL = "https://v2.jokeapi.dev/joke/Miscellaneous,Dark?amount=10"
HUMOR_API_URL = "https://api.humorapi.com/jokes/search?number=10&include-tags="
DAD_JOKE_API_URL = "https://icanhazdadjoke.com/search?limit=10"

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

# -------------------- Music Configuration -------------------- #
LAVALIST_URL = "https://lavalink-list.ajieblogs.eu.org/All"
LAVALINK_API_URL = "https://lavalink-api.appujet.site/api/nodes"

SOURCE_PATTERNS = [
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

SUPPORTED_PLATFORMS = (
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

SONG_STRIP = (
    ";",
    "*",
    "https:",
    "http:",
    "/",
)


# -------------------- RadioGarden Configuration -------------------- #
RADIOGARDEN_PLACES_URL = "https://radio.garden/api/ara/content/places"
RADIOGARDEN_PAGE_URL = "https://radio.garden/api/ara/content/page/"
RADIOGARDEN_SEARCH_URL = "https://radio.garden/api/search?q="
RADIOGARDEN_LISTEN_URL = "https://radio.garden/api/ara/content/listen/"

# -------------------- Wordnik API -------------------- #
WORDNIK_API_KEY = os.getenv("WORDNIK_API_KEY")
WORDNIK_API_URL = "https://api.wordnik.com/v4/words.json/wordOfTheDay?api_key="
