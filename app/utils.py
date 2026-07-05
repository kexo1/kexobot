import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any

import discord
import httpx
import sonolink
import sonolink.models as sl_models

from app.config.colors import COLOR_GREEN
from app.config.discord import ICON_YOUTUBE
from app.config.music import MUSIC_TO_REMOVE


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


def get_track_requester_name(track: sl_models.Playable) -> str:
    """Get the requester name from a track's extras.

    Parameters
    ----------
    track: :class:`sonolink.Playable`
        The track to get the requester name from.

    Returns
    -------
    str
        The requester name, or ``"Unknown"`` if not set.
    """
    return getattr(track.extras, "requester_name", "Unknown")


def get_track_requester_avatar(track: sl_models.Playable) -> str | None:
    """Get the requester avatar URL from a track's extras.

    Parameters
    ----------
    track: :class:`sonolink.Playable`
        The track to get the requester avatar from.

    Returns
    -------
    str | None
        The requester avatar URL, or ``None`` if not set.
    """
    return getattr(track.extras, "requester_avatar", None)


def make_now_playing_embed(track: sl_models.Playable) -> discord.Embed:
    """Create a 'Now playing' embed for a given track.

    Parameters
    ----------
    track: :class:`sonolink.Playable`
        The track to create the embed for.

    Returns
    -------
    :class:`discord.Embed`
        The embed to send.
    """
    embed = discord.Embed(
        color=COLOR_GREEN,
        title="Now playing",
        description=f"[**{fix_audio_title(track)}**]({track.uri})",
    )

    requester_name = get_track_requester_name(track)
    requester_avatar = get_track_requester_avatar(track)

    if not track.autoplay:
        embed.set_footer(
            text=f"Requested by {requester_name}",
            icon_url=requester_avatar,
        )
    else:
        embed.set_footer(
            text="YouTube Autoplay",
            icon_url=ICON_YOUTUBE,
        )

    embed.set_thumbnail(url=track.artwork)
    return embed


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
