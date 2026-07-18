from typing import Any, Callable

import discord

from app.config.colors import COLOR_BLUE, COLOR_RED


def make_embed(
    description: str,
    *,
    color: discord.Color = COLOR_BLUE,
    footer: str | None = None,
) -> discord.Embed:
    """Build a simple embed for one-off command responses."""
    embed = discord.Embed(title="", description=description, color=color)
    if footer:
        embed.set_footer(text=footer)
    return embed


def _no_track_found(to_find: str) -> discord.Embed:
    return make_embed(
        f":x: No tracks with index {to_find} were found in the queue. "
        + "Type `/music queue` to see the list of tracks."
    )


def _no_tracks_found(search: str) -> discord.Embed:
    return make_embed(f":x: No tracks were found for `{search}`.")


def _radiomap_no_station_found(search: str) -> discord.Embed:
    return make_embed(f":x: No station found with name {search}.")


def _queue_track_removed(title: str, uri: str) -> discord.Embed:
    return make_embed(f":wastebasket: Removed [{title}]({uri})")


def _queue_loop_enabled(count: int) -> discord.Embed:
    return make_embed(f"🔁 Looping queue with `({count}` songs)")


def _track_loop_enabled(title: str, uri: str) -> discord.Embed:
    return make_embed(f"🔁 Looping [{title}]({uri})")


def _reconnected_node(node: str) -> discord.Embed:
    return make_embed(f":white_check_mark: Reconnected to node `{node}`.")


type ResponseBuilder = Callable[..., discord.Embed]


RESPONSE_CODES: dict[str, discord.Embed | ResponseBuilder] = {
    # ──────────────────────────── Music errors ───────────────────────────── #
    "NO_VOICE_CHANNEL": make_embed(
        ":x: You're not in a voice channel. Type `/music play` from vc."
    ),
    "NOT_IN_SAME_VOICE_CHANNEL": make_embed(
        ":x: I am playing in a different voice channel."
    ),
    "NO_TRACK_FOUND_IN_QUEUE": _no_track_found,
    "NO_PERMISSIONS": make_embed(
        ":x: I don't have permissions to join your channel.", color=COLOR_RED
    ),
    "NO_NODE_INFO": make_embed(":x: Failed to get node info.", color=COLOR_RED),
    "NODE_CONNECT_FAILURE": make_embed(
        ":x: Failed to reconnect node.", color=COLOR_RED
    ),
    "NODE_NOT_FOUND": make_embed(
        ":x: Couldn't find node to play this music, try switching to a different node "
        + "with `/node reconnect`, or use Youtube links instead of Spotify/Deezer/Apple Music.",
        color=COLOR_RED,
    ),
    "NO_TRACKS_FOUND": _no_tracks_found,
    "NO_TRACKS_IN_QUEUE": make_embed("Queue is empty."),
    "RADIOMAP_ERROR": make_embed(
        ":x: Failed to get response from RadioMap API, try again later.",
        color=COLOR_RED,
    ),
    "RADIOMAP_NO_STATION_FOUND": _radiomap_no_station_found,
    "JOKE_TIMEOUT": make_embed(
        ":x: Failed to get joke, try again later.", color=COLOR_RED
    ),
    "NO_MORE_JOKES": make_embed(
        ":x: You've seen all available jokes for now.", color=COLOR_RED
    ),
    "QUEUE_CLEARED": make_embed(":wastebasket: Queue has been cleared."),
    "QUEUE_TRACK_REMOVED": _queue_track_removed,
    "QUEUE_SHUFFLED": make_embed("🔀 Queue shuffled."),
    "QUEUE_LOOP_DISABLED": make_embed("No longer looping queue."),
    "QUEUE_LOOP_ENABLED": _queue_loop_enabled,
    "TRACK_LOOP_DISABLED": make_embed("No longer looping current song."),
    "TRACK_LOOP_ENABLED": _track_loop_enabled,
    "RECONNECTED_NODE": _reconnected_node,
}


async def defer_interaction(
    interaction: discord.Interaction, ephemeral: bool = False
) -> None:
    if interaction.response.is_done():
        return
    await interaction.response.defer(ephemeral=ephemeral)


def _build_send_kwargs(
    *,
    content: str | None = None,
    embed: discord.Embed | None = None,
    embeds: list[discord.Embed] | None = None,
    view: discord.ui.View | None = None,
    files: list[discord.File] | None = None,
    suppress: bool | None = None,
    ephemeral: bool | None = None,
) -> dict[str, Any]:
    """Build keyword arguments dict for discord send methods, omitting None values."""
    kwargs: dict[str, Any] = {}
    if content is not None:
        kwargs["content"] = content
    if embed is not None:
        kwargs["embed"] = embed
    if embeds is not None:
        kwargs["embeds"] = embeds
    if view is not None:
        kwargs["view"] = view
    if files is not None:
        kwargs["files"] = files
    if suppress is not None:
        kwargs["suppress_embeds"] = suppress
    if ephemeral is not None:
        kwargs["ephemeral"] = ephemeral
    return kwargs


async def send(
    target: discord.Interaction | discord.abc.Messageable,
    content: str | None = None,
    *,
    code: str | None = None,
    embed: discord.Embed | None = None,
    embeds: list[discord.Embed] | None = None,
    view: discord.ui.View | None = None,
    files: list[discord.File] | None = None,
    delete_after: float | None = None,
    ephemeral: bool = False,
    suppress: bool | None = None,
    **kwargs: Any,  # pyright: ignore[reportAny]
) -> discord.Message | None:
    """Unified send function — the one entry point for all bot messages.

    Parameters
    ----------
    target: :class:`discord.Interaction` | :class:`discord.abc.Messageable`
        Where to send. If an ``Interaction`` it will try ``response.send_message``
        → ``followup.send`` → ``channel.send`` (auto-detects ``is_done()``).
    content: :class:`str` | ``None``
        Plain text content.
    code: :class:`str` | ``None``
        A key from ``RESPONSE_CODES``.  When given, the resolved embed takes
        precedence over ``embed`` / ``embeds`` (*you would not pass both*).
    embed, embeds, view, files, delete_after, suppress, ephemeral:
        Forwarded to the underlying Discord send method.
    **kwargs
        Any extra keyword arguments are passed to callable response builders.

    Returns
    -------
    :class:`discord.Message` | ``None``
        The sent message when available (interaction followups or channel
        sends), ``None`` when the interaction was a fresh response.
    """
    # ── 1. Resolve response code ───────────────────────────────────────────
    resolved_embed: discord.Embed | None = embed
    if code is not None:
        if code not in RESPONSE_CODES:
            raise ValueError(f"Unknown response code: {code}")
        response = RESPONSE_CODES[code]
        if callable(response):
            response = response(**kwargs)
        resolved_embed = response  # type: ignore[assignment]

    # ── 2. Route to the correct backend ────────────────────────────────────
    message: discord.Message | None = None

    if isinstance(target, discord.Interaction):
        payload = _build_send_kwargs(
            content=content,
            embed=resolved_embed if embeds is None else None,
            embeds=embeds,
            view=view,
            files=files,
            suppress=suppress,
        )

        if target.response.is_done():
            try:
                message = await target.followup.send(
                    **payload,  # pyright: ignore[reportAny]
                    ephemeral=ephemeral,
                    wait=True,
                )
            except discord.NotFound:
                if not ephemeral and target.channel:
                    try:
                        message = await target.channel.send(**payload)  # pyright: ignore[reportAny, reportUnknownVariableType, reportUnknownMemberType]
                    except discord.HTTPException:
                        pass
        else:
            try:
                await target.response.send_message(**payload, ephemeral=ephemeral)  # pyright: ignore[reportAny]
            except discord.NotFound:
                if not ephemeral and target.channel:
                    try:
                        message = await target.channel.send(**payload)  # pyright: ignore[reportAny, reportUnknownVariableType, reportUnknownMemberType]
                    except discord.HTTPException:
                        pass
            else:
                try:
                    message = await target.original_response()
                except discord.NotFound:
                    message = None
    else:
        # --- Channel / Messageable path ---
        payload = _build_send_kwargs(
            content=content,
            embed=resolved_embed if embeds is None else None,
            embeds=embeds,
            view=view,
            files=files,
            suppress=suppress,
        )
        try:
            message = await target.send(**payload)  # pyright: ignore[reportAny]
        except discord.HTTPException:
            pass

    if message and delete_after is not None:
        await message.delete(delay=delete_after)  # pyright: ignore[reportUnknownMemberType]

    return message  # pyright: ignore[reportUnknownVariableType]
