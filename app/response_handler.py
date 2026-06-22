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


async def send_embed(
    ctx: discord.Interaction | discord.TextChannel,
    embed: discord.Embed,
    *,
    respond: bool = True,
    ephemeral: bool = True,
    delete_after: int | None = None,
) -> None:
    """Send a one-off embed without using a response code."""
    if respond and isinstance(ctx, discord.Interaction):
        await send_interaction(
            ctx,
            embed=embed,
            ephemeral=ephemeral,
            delete_after=delete_after,
        )
        return

    if isinstance(ctx, discord.Interaction):
        await send_interaction(ctx, embed=embed, delete_after=delete_after)
    else:
        await send_message(ctx, embed=embed, delete_after=delete_after)


async def send_response(
    ctx: discord.Interaction | discord.TextChannel,
    response_code: str,
    respond: bool = True,
    ephemeral: bool = True,
    delete_after: int | None = None,
    **kwargs: Any,
) -> None:
    """This method sends a response to the user based on the response code.

    Parameters
    ----------
    ctx: :class:`discord.Interaction`
        The context of the command.
    response_code: :class:`str`
        The response code to determine the type of response.
    respond: :class:`bool`
        Whether to respond to the user or send a message in the channel.
    ephemeral: :class:`bool`
        Whether the response should be ephemeral (only visible to the user).
    delete_after: :class:`int`
        The time in seconds after which the response should be deleted.
    kwargs: :class:`Any`
        Additional keyword arguments to pass to the response handler.

    Raises
    ------
    ValueError
        If the response code is not recognized.
    """
    if response_code not in RESPONSE_CODES:
        raise ValueError(f"Unknown response code: {response_code}")

    response = RESPONSE_CODES[response_code]
    if callable(response):
        response = response(**kwargs)

    await send_embed(
        ctx,
        response,
        respond=respond,
        ephemeral=ephemeral,
        delete_after=delete_after,
    )


async def defer_interaction(
    interaction: discord.Interaction, ephemeral: bool = False
) -> None:
    if interaction.response.is_done():
        return
    await interaction.response.defer(ephemeral=ephemeral)


async def send_interaction(
    interaction: discord.Interaction,
    content: str | None = None,
    *,
    embed: discord.Embed | None = None,
    embeds: list[discord.Embed] | None = None,
    view: discord.ui.View | None = None,
    files: list[discord.File] | None = None,
    delete_after: float | None = None,
    suppress: bool | None = None,
    ephemeral: bool = False,
) -> discord.Message | None:
    payload: dict[str, Any] = {"ephemeral": ephemeral}

    if content is not None:
        payload["content"] = content
    if view is not None:
        payload["view"] = view

    # discord.py rejects sending both "embed" and "embeds" together.
    if embeds is not None:
        payload["embeds"] = embeds
    elif embed is not None:
        payload["embed"] = embed

    if files is not None:
        payload["files"] = files
    if suppress is not None:
        payload["suppress_embeds"] = suppress

    message: discord.Message | None = None
    channel_payload = {
        key: value for key, value in payload.items() if key != "ephemeral"
    }
    if interaction.response.is_done():
        try:
            message = await interaction.followup.send(**payload, wait=True)
        except discord.NotFound:
            if not ephemeral and interaction.channel:
                message = await interaction.channel.send(**channel_payload)
    else:
        try:
            await interaction.response.send_message(**payload)
        except discord.NotFound:
            if not ephemeral and interaction.channel:
                message = await interaction.channel.send(**channel_payload)
        else:
            try:
                message = await interaction.original_response()
            except discord.NotFound:
                message = None

    if message and delete_after:
        await message.delete(delay=delete_after)
    return message


async def send_message(
    ctx: discord.TextChannel,
    embed: discord.Embed | None = None,
    embeds: list[discord.Embed] | None = None,
    view: discord.ui.View | None = None,
    files: list[discord.File] | None = None,
    delete_after: int | None = None,
) -> None:
    """Sends a message to the channel, not as an interaction."""

    try:
        await ctx.send(
            embed=embed,
            embeds=embeds,
            view=view,
            files=files,
            delete_after=delete_after,
        )
    except discord.HTTPException:
        pass
