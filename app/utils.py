import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, Callable

import discord
import httpx
import sonolink
import sonolink.models as sl_models

from app.config.music import MUSIC_TO_REMOVE
from app.config.reddit import SHITPOST_SUBREDDITS_DEFAULT


def load_text_file(name: str) -> list[str]:
    """Load a text file and return its content as lines.

    Parameters
    ----------
    name: str
        The name of the text file to load (without the .txt extension).
    """
    with open(f"text_files/{name}.txt", encoding="utf8") as f:
        return f.read().splitlines()


def average(numbers: list[float | int]) -> float:
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


def get_url_response_time(url: str) -> int:
    """Get the response time of a URL in seconds.

    Parameters
    ----------
    url: str
        The URL to check the response time of.

    Returns
    -------
    float
        The response time of the URL in seconds, or 0.0 if the request failed.
    """
    try:
        start_time = time.perf_counter()
        httpx.get(url, timeout=5)
        return int((time.perf_counter() - start_time) * 1000)  # Convert to milliseconds
    except httpx.RequestError:
        return 9999


def strip_text(text: str, to_strip: tuple[str, ...]) -> str:
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


def fix_audio_title(track: sl_models.Playable) -> str:
    """Fix the title of an audio track by removing unwanted characters.

    Parameters
    ----------
    track: :class:`sonolink.Playable`
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

    for char in MUSIC_TO_REMOVE:
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


def find_track(player: sonolink.Player, to_find: str) -> int | None:
    """Find a track in the player's queue by title or index.

    Parameters
    ----------
    player: :class:`sonolink.Player`
        The sonolink Player instance.
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


def generate_temp_guild_data() -> dict:
    """Generate temporary guild data for the bot.

    Returns
    -------
    dict
        A dictionary containing temporary guild data.
    """
    return {
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
    fixed_data: dict[str, Any], generator: Callable[[], dict[str, Any]]
) -> dict[str, Any]:
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


async def make_http_request(
    session: httpx.AsyncClient,
    url: str,
    data: dict[str, Any] | None = None,
    headers: dict[str, Any] | None = None,
    retries: int = 2,
    timeout: float = 3.0,
    get_json: bool = False,
    binary: bool = False,
) -> httpx.Response | Any | None:
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
    :class:`httpx.Response` | dict | list | None
        The response object (or parsed JSON) from the request, or None if the request failed.
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
                logging.warning(f"[Httpx] Request failed ({type(e).__name__}): {url}")
                return None
            await asyncio.sleep(1 * (attempt + 1))
        except json.decoder.JSONDecodeError:
            logging.warning("[Httpx] Failed to decode JSON: %s", url)
    return None


# noinspection PyUnusedLocal
class EmbedPaginator(discord.ui.View):
    """A paginator for displaying embeds that are too long for Discord.

    This view creates two buttons, "Previous" and "Next",
    that allow the user to navigate through the pages of embeds.

    Parameters
    ----------
    embeds : list[discord.Embed]
        A list of embeds to be displayed in the paginator.
    timeout : int
        The time in seconds before the paginator times out. Default is 600 seconds.
    """

    def __init__(self, embeds: list[discord.Embed], timeout: int = 600) -> None:
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
        self, interaction: discord.Interaction, button: discord.ui.Button
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
        self, interaction: discord.Interaction, button: discord.ui.Button
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
