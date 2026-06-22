"""Music / radio configuration: URLs, source patterns, platform registry, emojis."""

import re
from enum import Enum

############################# Radio Garden API URLs ############################
API_RADIOGARDEN_PLACES = "https://radio.garden/api/ara/content/places"
API_RADIOGARDEN_PAGE = "https://radio.garden/api/ara/content/page/"
API_RADIOGARDEN_SEARCH = "https://radio.garden/api/search?q="
API_RADIOGARDEN_LISTEN = "https://radio.garden/api/ara/content/listen/"

############################# Music Sources ############################
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

############################# Music Tips ############################
MUSIC_TIPS: dict[int, str] = {
    3: (
        "-# Not happy with the current node performance?\n"
        "-# You can switch between {node_count} nodes "
        "by using /node reconnect."
    ),
    10: (
        "-# Use the /music autoplay_mode command and\n"
        "-# set the mode to populated to enable automatic queuing of "
        "similar tracks."
    ),
    15: (
        "-# Would you like to see which platforms are supported by this "
        "node? Use the /node supported_platforms."
    ),
}


############################# Node Supported Platforms ############################
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

############################# Music To Remove ############################
MUSIC_TO_REMOVE = (
    ";",
    "*",
    "https:",
    "http:",
    "/",
)
