from typing import Dict, Callable, Any, Union

import discord

ResponseHandler = Callable[[discord.ApplicationContext], discord.Embed]

RESPONSE_CODES: Dict[str, ResponseHandler] = {
    # Error responses
    "NO_VOICE_CHANNEL": discord.Embed(
        title="",
        description=":x: You're not in a voice channel. Type `/play` from vc.",
        color=discord.Color.blue(),
    ),
    "NOT_IN_VOICE_CHANNEL": discord.Embed(
        title="",
        description=":x: I'm not joined in a voice channel.",
        color=discord.Color.blue(),
    ),
    "NOT_IN_SAME_VOICE_CHANNEL": discord.Embed(
        title="",
        description=":x: I am playing in a different voice channel.",
        color=discord.Color.blue(),
    ),
    "NOT_IN_SAME_VOICE_CHANNEL_PLAYING": discord.Embed(
        title="",
        description=":x: I am playing in a different voice channel, wait till song finishes.",
        color=discord.Color.blue(),
    ),
    "NOT_PLAYING": discord.Embed(
        title="",
        description=":x: I'm not playing anything. Type `/play` from vc.",
        color=discord.Color.blue(),
    ),
    "NO_TRACK_FOUND_IN_QUEUE": lambda **kwargs: discord.Embed(
        title="",
        description=f":x: No tracks with index {kwargs.get('to_find')} were found in the queue."
        " Type `/queue` to see the list of tracks.",
        color=discord.Color.blue(),
    ),
    "NO_PERMISSIONS": discord.Embed(
        title="",
        description=":x: I don't have permissions to join your channel.",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "NO_NODES": discord.Embed(
        title="",
        description=":x: No nodes are currently assigned to the bot.\n"
        "To fix this, use command `/node reconnect`",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "NO_NODE_INFO": discord.Embed(
        title="",
        description=":x: Failed to get node info.",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "NO_NODES_CONNECTED": discord.Embed(
        title="",
        description=":x: No nodes are connected.",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "NODE_CONNECT_FAILURE": lambda **kwargs: discord.Embed(
        title="",
        description=f":x: Failed to connect to `{kwargs.get('uri')}`",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "NODE_UNRESPONSIVE": discord.Embed(
        title="",
        description=":warning: Node is unresponsive, trying to connect to a new node.",
        color=discord.Color.yellow(),
    ),
    "NO_PLAYERS_CONNECTED": discord.Embed(
        title="",
        description=":x: No players are playing music.",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "CONNECTION_TIMEOUT": discord.Embed(
        title="",
        description=":x: Failed to connect to the voice channel,"
        " might be due to being manually disconnected or node is unresponsive."
        "\nTry using `/node reconnect`.",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "NO_TRACKS_FOUND": lambda **kwargs: discord.Embed(
        title="",
        description=f":x: No tracks were found for `{kwargs.get('search')}`.",
        color=discord.Color.blue(),
    ),
    "NO_TRACKS_IN_QUEUE": discord.Embed(
        title="",
        description="Queue is empty.",
        color=discord.Color.blue(),
    ),
    "ALREADY_PAUSED": discord.Embed(
        title="",
        description=":x: Song is already paused.",
        color=discord.Color.blue(),
    ),
    "CANT_SHUFFLE": discord.Embed(
        title="",
        description=":exploding_head: Can't shuffle 1 song in queue BRUH",
        color=discord.Color.blue(),
    ),
    "YOUTUBE_ERROR": discord.Embed(
        title="",
        description=":x: Failed to load tracks, youtube plugin"
        " might be disabled, or version is outdated."
        " Try `/node reconnect`.\nIf issue persists,"
        " it means YouTube updated their site and getting"
        " tracks won't work until youtube plugin gets fixed.",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "LAVALINK_ERROR": discord.Embed(
        title="",
        description=":x: Failed to load tracks, you probably inputted"
        " wrong link or this Lavalink server doesn't have "
        "necessary plugins.\nTo fix this, use command `/node reconnect`",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "NODE_REQUEST_ERROR": lambda **kwargs: discord.Embed(
        title="",
        description=":warning: An error occured when trying to send"
        " request to the node, trying to connect to a new node."
        f"\n\n**Message: {kwargs.get('error')}**",
        color=discord.Color.yellow(),
    ),
    "JOKE_TIMEOUT": discord.Embed(
        title="",
        description=":x: Failed to get joke, try again later.",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "TRACK_EXCEPTION": lambda **kwargs: discord.Embed(
        title="",
        description=":warning: An error occured when playing song, trying to connect to a new node."
        f"\n\n**Message**: {kwargs.get('message')}"
        f"\n**Severity**: {kwargs.get('severity')}",
        color=discord.Color.yellow(),
    ),
    "TRACK_STUCK": discord.Embed(
        title="",
        description=":warning: Track got stuck, trying to connect to a new node.",
        color=discord.Color.yellow(),
    ),
    "RADIOMAP_ERROR": discord.Embed(
        title="",
        description=":x: Failed to get response from RadioMap API, try again later.",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "RADIOMAP_NO_STATION_FOUND": lambda **kwargs: discord.Embed(
        title="",
        description=f":x: No station found with name {kwargs.get('search')}.",
        color=discord.Color.blue(),
    ),
    "CHANNEL_NOT_NSFW": discord.Embed(
        title="",
        description=":x: You have set NSFW posts to true,"
        " yet the channel you requested in is not NSFW,"
        " skipping shitpost.",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "NOT_OWNER": discord.Embed(
        title="",
        description=":x: Only bot owner can use this command.",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "REDDIT_REQUEST_ERROR": discord.Embed(
        title="",
        description=":x: Reddit didn't respond, try again in a minute.\nWhat could cause "
        "error? - Reddit is down, Subreddit is locked, API might be overloaded",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "SFD_SERVER_NOT_FOUND": discord.Embed(
        title="",
        description=":x: Server you searched for is not in the list, "
        " make sure you parsed correct server name.",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "SFD_SERVERS_NOT_FOUND": discord.Embed(
        title="",
        description=":x: No servers are online or API might be down.",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "CANT_PING_ROLE": discord.Embed(
        title="",
        description=":x: I can't ping Exotic role, please check if role exists or"
        " if I have permission to ping it.",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "NOT_EMBED_AUTHOR": discord.Embed(
        title="",
        description=":x: You are not author of this embed.",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "ALREADY_HOSTING": discord.Embed(
        title="",
        description=":x: You have already created host embed!\n"
        "Click on button embed to stop it from beign active.",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "INCORRECT_IMAGE_URL": discord.Embed(
        title="",
        description=":x: Image URL needs to end with .png, .gif and etc.",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "DB_ALREADY_IN_LIST": lambda **kwargs: discord.Embed(
        title="",
        description=f":x: String `{kwargs.get('to_upload')}`"
        f" is already in the list, use `/bot_config show`",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "DB_NOT_IN_LIST": lambda **kwargs: discord.Embed(
        title="",
        description=f":x: String `{kwargs.get('to_remove')}`"
        f" is already in the list, use `/bot_config show`",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    # -------------------- Success messages -------------------- #
    "TRACK_SKIPPED": discord.Embed(
        title="",
        description="**⏭️ Skipped**",
        color=discord.Color.blue(),
    ),
    "TRACK_SKIPPED_TO": lambda **kwargs: discord.Embed(
        title="",
        description=f"**⏭️ Skipped to [{kwargs.get('title')}]({kwargs.get('uri')})**",
        color=discord.Color.blue(),
    ),
    "QUEUE_CLEARED": discord.Embed(
        title="",
        description="**:wastebasket: Queue has been cleared.**",
        color=discord.Color.blue(),
    ),
    "QUEUE_TRACK_REMOVED": lambda **kwargs: discord.Embed(
        title="",
        description=f"**:wastebasket: Removed [{kwargs.get('title')}]({kwargs.get('uri')})**",
        color=discord.Color.blue(),
    ),
    "QUEUE_SHUFFLED": discord.Embed(
        title="",
        description="**🔀 Queue shuffled!**",
        color=discord.Color.blue(),
    ),
    "QUEUE_LOOP_DISABLED": discord.Embed(
        title="",
        description="**✅ No longer looping queue.**",
        color=discord.Color.blue(),
    ),
    "QUEUE_LOOP_ENABLED": lambda **kwargs: discord.Embed(
        title="",
        description=f"**🔁 Looping queue with `({kwargs.get('count')}` songs)**",
        color=discord.Color.blue(),
    ),
    "TRACK_LOOP_DISABLED": discord.Embed(
        title="",
        description="**✅ No longer looping current song.**",
        color=discord.Color.blue(),
    ),
    "TRACK_LOOP_ENABLED": lambda **kwargs: discord.Embed(
        title="",
        description=f"**🔁 Looping [{kwargs.get('title')}]({kwargs.get('uri')})**",
        color=discord.Color.blue(),
    ),
    "VOLUME_CHANGED": lambda **kwargs: discord.Embed(
        title="",
        description=f"**🔊 Volume set to `{kwargs.get('volume')}%`**",
        color=discord.Color.blue(),
    ),
    "TRACK_PAUSED": discord.Embed(
        title="",
        description="**⏸️ Paused**",
        color=discord.Color.blue(),
        footer=discord.EmbedFooter(text="Deleting in 10s."),
    ),
    "TRACK_RESUMED": discord.Embed(
        title="",
        description="**:arrow_forward: Resumed**",
        color=discord.Color.blue(),
        footer=discord.EmbedFooter(text="Deleting in 10s."),
    ),
    "DISCONNECTED": lambda **kwargs: discord.Embed(
        title="",
        description=f"**✅ Left <#{kwargs.get('channel_id')}>**",
        color=discord.Color.blue(),
    ),
    "DISCONNECTED_INACTIVITY": lambda **kwargs: discord.Embed(
        title="",
        description=f"**Left <#{kwargs.get('channel_id')}> after 10 minutes of inactivity.**",
        color=discord.Color.blue(),
    ),
    "DISCONNECTED_NO_USERS": lambda **kwargs: discord.Embed(
        title="",
        description=f"**Left <#{kwargs.get('channel_id')}>, no users in channel.**",
        color=discord.Color.blue(),
    ),
    "DISCONNECTED_MANUALLY": lambda **kwargs: discord.Embed(
        title="",
        description=f"**Disconnected from <#{kwargs.get('channel_id')}>,"
        f" please next time use command `/leave`**",
        color=discord.Color.blue(),
    ),
    "JOINED": lambda **kwargs: discord.Embed(
        title="",
        description=f"**✅ Joined to <#{kwargs.get('channel_id')}>"
        f" and set text channel to <#{kwargs.get('text_channel_id')}>.**",
        color=discord.Color.blue(),
    ),
    "MOVED": lambda **kwargs: discord.Embed(
        title="",
        description=f"**:wheelchair: Moving to <#{kwargs.get('channel_id')}>**",
        color=discord.Color.blue(),
    ),
    "CURRENT_VOLUME": lambda **kwargs: discord.Embed(
        title="",
        description=f"**🔊 `{kwargs.get('volume')}%`**",
        color=discord.Color.blue(),
    ),
    "SPEED_CHANGED": lambda **kwargs: discord.Embed(
        title="",
        description=f"**:stopwatch:  Speed increased by `{kwargs.get('multiplier')}x`**",
        color=discord.Color.blue(),
    ),
    "EFFECTS_CLEARED": discord.Embed(
        title="",
        description="**:microphone:  Effects were cleared.**",
        color=discord.Color.blue(),
        footer=discord.EmbedFooter(text="takes 3 seconds to apply"),
    ),
    "AUTOPLAY_MODE_CHANGED": lambda **kwargs: discord.Embed(
        title="",
        description=f"**:repeat: Autoplay mode set to `{kwargs.get('autoplay_mode')}`**",
        color=discord.Color.blue(),
    ),
    "NODE_CONNECT_SUCCESS": lambda **kwargs: discord.Embed(
        title="",
        description=f"**✅ Connected to node `{kwargs.get('uri')}`**",
        color=discord.Color.blue(),
    ),
    "NODE_RECONNECT_TO_PLAYER_SUCCESS": lambda **kwargs: discord.Embed(
        title="",
        description=f"**✅ Reconnected your player to node `{kwargs.get('uri')}`**",
        color=discord.Color.blue(),
    ),
    "NODE_RECONNECT_SUCCESS": lambda **kwargs: discord.Embed(
        title="",
        description=f"**✅ Reconnected to node `{kwargs.get('uri')}`**",
        color=discord.Color.blue(),
    ),
    "USER_DATA_GENERATED": lambda **kwargs: discord.Embed(
        title="",
        description="**:floppy_disk:  Generated user data.**",
        color=discord.Color.blue,
    ),
    "DB_ADDED": lambda **kwargs: discord.Embed(
        title="",
        description=f"✅ String `{kwargs.get('to_upload')}`"
        f" was added to `{kwargs.get('collection_name')}`",
        color=discord.Color.blue(),
    ),
    "DB_REMOVED": lambda **kwargs: discord.Embed(
        title="",
        description=f"✅ String `{kwargs.get('to_remove')}`"
        f" was removed from `{kwargs.get('collection_name')}`",
        color=discord.Color.blue(),
    ),
}


async def send_response(
    ctx: Union[discord.ApplicationContext, discord.TextChannel],
    response_code: str,
    respond: bool = True,
    ephemeral: bool = True,
    delete_after: int = None,
    **kwargs: Any,
) -> None:
    """This method sends a response to the user based on the response code.

    Parameters
    ----------
    ctx: :class:`discord.ApplicationContext`
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

    if respond:
        await ctx.respond(
            embed=response, ephemeral=ephemeral, delete_after=delete_after
        )
    else:
        await ctx.send(embed=response, delete_after=delete_after)
