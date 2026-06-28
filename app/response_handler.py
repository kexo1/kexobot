from typing import Any, Callable

import discord

from app.config.colors import COLOR_BLUE, COLOR_RED

ResponseBuilder = Callable[..., discord.Embed]


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


# Only messages reused in multiple places belong here.
RESPONSE_CODES: dict[str, discord.Embed | ResponseBuilder] = {
    # ──────────────────────────── Music errors ───────────────────────────── #
    "NO_VOICE_CHANNEL": make_embed(
        ":x: You're not in a voice channel. Type `/music play` from vc."
    ),
    "NOT_IN_SAME_VOICE_CHANNEL": make_embed(
        ":x: I am playing in a different voice channel."
    ),
    "NO_TRACK_FOUND_IN_QUEUE": lambda **kwargs: make_embed(
        f":x: No tracks with index {kwargs.get('to_find')} were found in the queue."
        " Type `/music queue` to see the list of tracks."
    ),
    "NO_PERMISSIONS": make_embed(
        ":x: I don't have permissions to join your channel.", color=COLOR_RED
    ),
    "NO_NODE_INFO": make_embed(":x: Failed to get node info.", color=COLOR_RED),
    "NODE_CONNECT_FAILURE": make_embed(
        ":x: Failed to reconnect node.", color=COLOR_RED
    ),
    "NODE_NOT_FOUND": make_embed(
        ":x: Couldn't find node to play this music, try switching to a different node "
        "with `/node reconnect`, or use Youtube links instead of Spotify/Deezer/Apple Music.",
        color=COLOR_RED,
    ),
    "NO_TRACKS_FOUND": lambda **kwargs: make_embed(
        f":x: No tracks were found for `{kwargs.get('search')}`."
    ),
    "NO_TRACKS_IN_QUEUE": make_embed("Queue is empty."),
    "RADIOMAP_ERROR": make_embed(
        ":x: Failed to get response from RadioMap API, try again later.",
        color=COLOR_RED,
    ),
    "RADIOMAP_NO_STATION_FOUND": lambda **kwargs: make_embed(
        f":x: No station found with name {kwargs.get('search')}."
    ),
    "JOKE_TIMEOUT": make_embed(
        ":x: Failed to get joke, try again later.", color=COLOR_RED
    ),
    "NO_MORE_JOKES": make_embed(
        ":x: You've seen all available jokes for now.", color=COLOR_RED
    ),
    "QUEUE_CLEARED": make_embed(":wastebasket: Queue has been cleared."),
    "QUEUE_TRACK_REMOVED": lambda **kwargs: make_embed(
        f":wastebasket: Removed [{kwargs.get('title')}]({kwargs.get('uri')})"
    ),
    "QUEUE_SHUFFLED": make_embed("🔀 Queue shuffled."),
    "QUEUE_LOOP_DISABLED": make_embed("No longer looping queue."),
    "QUEUE_LOOP_ENABLED": lambda **kwargs: make_embed(
        f"🔁 Looping queue with `({kwargs.get('count')}` songs)"
    ),
    "TRACK_LOOP_DISABLED": make_embed("No longer looping current song."),
    "TRACK_LOOP_ENABLED": lambda **kwargs: make_embed(
        f"🔁 Looping [{kwargs.get('title')}]({kwargs.get('uri')})"
    ),
    "RECONNECTED_NODE": lambda **kwargs: make_embed(
        f":white_check_mark: Reconnected to node `{kwargs.get('node')}`."
    ),
}


async def defer_interaction(
    interaction: discord.Interaction, ephemeral: bool = False
) -> None:
    if interaction.response.is_done():
        return
    await interaction.response.defer(ephemeral=ephemeral)


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
    **kwargs: Any,
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

    # ── 2. Build the payload that both interaction + channel paths need ─────
    payload: dict[str, Any] = {}
    if content is not None:
        payload["content"] = content
    if view is not None:
        payload["view"] = view
    if embeds is not None:
        payload["embeds"] = embeds
    elif resolved_embed is not None:
        payload["embed"] = resolved_embed
    if files is not None:
        payload["files"] = files
    if suppress is not None:
        payload["suppress_embeds"] = suppress

    # ── 3. Route to the correct backend ────────────────────────────────────
    message: discord.Message | None = None

    if isinstance(target, discord.Interaction):
        # --- Interaction path ---
        interaction_payload: dict[str, Any] = {**payload, "ephemeral": ephemeral}

        if target.response.is_done():
            try:
                message = await target.followup.send(**interaction_payload, wait=True)
            except discord.NotFound:
                if not ephemeral and target.channel:
                    channel_payload = {
                        k: v for k, v in payload.items() if k != "ephemeral"
                    }
                    try:
                        message = await target.channel.send(**channel_payload)
                    except discord.HTTPException:
                        pass
        else:
            try:
                await target.response.send_message(**interaction_payload)
            except discord.NotFound:
                if not ephemeral and target.channel:
                    try:
                        message = await target.channel.send(**payload)
                    except discord.HTTPException:
                        pass
            else:
                try:
                    message = await target.original_response()
                except discord.NotFound:
                    message = None
    else:
        # --- Channel / Messageable path ---
        try:
            message = await target.send(**payload)
        except discord.HTTPException:
            pass

    if message and delete_after is not None:
        await message.delete(delay=delete_after)

    return message
