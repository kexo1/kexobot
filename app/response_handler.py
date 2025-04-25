from typing import Dict, Callable, Any

import discord

ResponseHandler = Callable[[discord.ApplicationContext], discord.Embed]

RESPONSE_CODES: Dict[str, ResponseHandler] = {
    # Error responses
    "NO_VOICE_CHANNEL": lambda ctx: discord.Embed(
        title="",
        description=f":x: You're not in a voice channel. Type `/play` from vc.",
        color=discord.Color.blue(),
    ),
    "NOT_IN_VOICE_CHANNEL": lambda ctx: discord.Embed(
        title="",
        description=f":x: I'm not joined in a voice channel.",
        color=discord.Color.blue(),
    ),
    "NOT_IN_SAME_VOICE_CHANNEL": lambda ctx: discord.Embed(
        title="",
        description=f":x: I am playing in a different voice channel.",
        color=discord.Color.blue(),
    ),
    "NOT_IN_SAME_VOICE_CHANNEL_PLAYING": lambda ctx: discord.Embed(
        title="",
        description=f":x: I am playing in a different voice channel, wait till song finishes.",
        color=discord.Color.blue(),
    ),
    "NOT_PLAYING": lambda ctx: discord.Embed(
        title="",
        description=f":x: I'm not playing anything. Type `/play` from vc.",
        color=discord.Color.blue(),
    ),
    "NO_TRACK_FOUND_IN_QUEUE": lambda ctx, **kwargs: discord.Embed(
        title="",
        description=f":x: No tracks with index {kwargs.get('to_find')} were found in the queue. Type `/queue` to see "
        f"the list of tracks.",
        color=discord.Color.blue(),
    ),
    "NO_PERMISSIONS": lambda ctx: discord.Embed(
        title="",
        description=":x: I don't have permissions to join your channel.",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "NO_NODES": lambda ctx: discord.Embed(
        title="",
        description=":x: No nodes are currently assigned to the bot.\nTo fix this, use command `/reconnect_node`",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "NO_NODES_CONNECTED": lambda ctx: discord.Embed(
        title="",
        description=":x: No nodes are connected.",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "NODE_CONNECT_FAILURE": lambda ctx, **kwargs: discord.Embed(
        title="",
        description=f":x: Failed to connect to `{kwargs.get('uri')}`",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "NODE_UNRESPONSIVE": lambda ctx: discord.Embed(
        title="",
        description=":x: Node is unresponsive, please use command `/reconnect_node`",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "NO_PLAYERS_CONNECTED": lambda ctx: discord.Embed(
        title="",
        description=":x: No players are playing music.",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "CONNECTION_TIMEOUT": lambda ctx: discord.Embed(
        title="",
        description=":x: Failed to connect to the voice channel, was bot moved manually? If yes disconnect it and try "
        "again.",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "NO_TRACKS_FOUND": lambda ctx, **kwargs: discord.Embed(
        title="",
        description=f":x: No tracks were found for `{kwargs.get('search')}`.",
        color=discord.Color.blue(),
    ),
    "NO_TRACKS_IN_QUEUE": lambda ctx: discord.Embed(
        title="",
        description="Queue is empty.",
        color=discord.Color.blue(),
    ),
    "ALREADY_PAUSED": lambda ctx: discord.Embed(
        title="",
        description=":x: Song is already paused.",
        color=discord.Color.blue(),
    ),
    "CANT_SHUFFLE": lambda ctx: discord.Embed(
        title="",
        description=":exploding_head: Can't shuffle 1 song in queue BRUH",
        color=discord.Color.blue(),
    ),
    "YOUTUBE_ERROR": lambda ctx: discord.Embed(
        title="",
        description=":x: Failed to load tracks, youtube plugin might be disabled, or version is outdated. Try "
        "`/reconnect_node`.\nIf issue persists, it means YouTube updated their site and getting tracks "
        "won't work until youtube plugin gets fixed.",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "LAVALINK_ERROR": lambda ctx: discord.Embed(
        title="",
        description=":x: Failed to load tracks, you probably inputted wrong link or this Lavalink server doesn't have "
        "necessary plugins.\nTo fix this, use command `/reconnect_node`",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "NODE_REQUEST_ERROR": lambda ctx: discord.Embed(
        title="",
        description=":x: Failed to connect to send request to the node.\nError might be caused by Discord servers not "
        "responding, give it a minute or use command `/reconnect_node`",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "RADIOMAP_ERROR": lambda ctx: discord.Embed(
        title="",
        description=":x: Failed to get response from RadioMap API, try again later.",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "CHANNEL_NOT_NSFW": lambda ctx: discord.Embed(
        title="",
        description=":x: You have set NSFW posts to true, yet the channel you requested in is not NSFW,"
        " skipping shitpost.",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "REDDIT_REQUEST_ERROR": lambda ctx: discord.Embed(
        title="",
        description=":x: Reddit didn't respond, try again in a minute.\nWhat could cause "
        "error? - Reddit is down, Subreddit is locked, API might be overloaded",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "SFD_SERVER_NOT_FOUND": lambda ctx: discord.Embed(
        title="",
        description=":x: Server you searched for is not in the list, "
        " make sure you parsed correct server name.",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "SFD_SERVERS_NOT_FOUND": lambda ctx: discord.Embed(
        title="",
        description=":x: No servers are online or API might be down.",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "CANT_PING_ROLE": lambda ctx: discord.Embed(
        title="",
        description=":x: I can't ping Exotic role, please check if role exists or"
        " if I have permission to ping it.",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "NOT_EMBED_AUTHOR": lambda ctx: discord.Embed(
        title="",
        description=":x: You are not author of this embed.",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "ALREADY_HOSTING": lambda ctx: discord.Embed(
        title="",
        description=":x: You have already created host embed!\nClick on button embed to stop it from beign active..",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "INCORRECT_IMAGE_URL": lambda ctx: discord.Embed(
        title="",
        description=":x: Image URL needs to end with .png, .gif and etc..",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "DB_ALREADY_IN_LIST": lambda ctx, **kwargs: discord.Embed(
        title="",
        description=f":x: String `{kwargs.get('to_upload')}` is already in the list, use `/bot_config show`",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "DB_NOT_IN_LIST": lambda ctx, **kwargs: discord.Embed(
        title="",
        description=f":x: String `{kwargs.get('to_remove')}` is already in the list, use `/bot_config show`",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    # -------------------- Success messages -------------------- #
    "TRACK_SKIPPED": lambda ctx: discord.Embed(
        title="",
        description="**⏭️ Skipped**",
        color=discord.Color.blue(),
    ),
    "TRACK_SKIPPED_TO": lambda ctx, **kwargs: discord.Embed(
        title="",
        description=f"**⏭️ Skipped to [{kwargs.get('title')}]({kwargs.get('uri')})**",
        color=discord.Color.blue(),
    ),
    "QUEUE_CLEARED": lambda ctx: discord.Embed(
        title="",
        description="**:wastebasket: Queue has been cleared.**",
        color=discord.Color.blue(),
    ),
    "QUEUE_TRACK_REMOVED": lambda ctx, **kwargs: discord.Embed(
        title="",
        description=f"**:wastebasket: Removed [{kwargs.get('title')}]({kwargs.get('uri')})**",
        color=discord.Color.blue(),
    ),
    "QUEUE_SHUFFLED": lambda ctx: discord.Embed(
        title="",
        description="**🔀 Queue shuffled!**",
        color=discord.Color.blue(),
    ),
    "QUEUE_LOOP_DISABLED": lambda ctx: discord.Embed(
        title="",
        description="**✅ No longer looping queue.**",
        color=discord.Color.blue(),
    ),
    "QUEUE_LOOP_ENABLED": lambda ctx, **kwargs: discord.Embed(
        title="",
        description=f"**🔁 Looping queue with `({kwargs.get('count')}` songs)**",
        color=discord.Color.blue(),
    ),
    "TRACK_LOOP_DISABLED": lambda ctx: discord.Embed(
        title="",
        description="**✅ No longer looping current song.**",
        color=discord.Color.blue(),
    ),
    "TRACK_LOOP_ENABLED": lambda ctx, **kwargs: discord.Embed(
        title="",
        description=f"**🔁 Looping [{kwargs.get('title')}]({kwargs.get('uri')})**",
        color=discord.Color.blue(),
    ),
    "VOLUME_CHANGED": lambda ctx, **kwargs: discord.Embed(
        title="",
        description=f"**🔊 Volume set to `{kwargs.get('volume')}%`**",
        color=discord.Color.blue(),
    ),
    "TRACK_PAUSED": lambda ctx: discord.Embed(
        title="",
        description="**⏸️ Paused**",
        color=discord.Color.blue(),
        footer=discord.EmbedFooter(text="Deleting in 10s."),
    ),
    "TRACK_RESUMED": lambda ctx: discord.Embed(
        title="",
        description="**:arrow_forward: Resumed**",
        color=discord.Color.blue(),
        footer=discord.EmbedFooter(text="Deleting in 10s."),
    ),
    "DISCONNECTED": lambda ctx, **kwargs: discord.Embed(
        title="",
        description=f"**✅ Left <#{kwargs.get('channel_id')}>**",
        color=discord.Color.blue(),
    ),
    "JOINED": lambda ctx, **kwargs: discord.Embed(
        title="",
        description=f"**✅ Joined to <#{kwargs.get('channel_id')}>"
        f" and set text channel to <#{kwargs.get('text_channel_id')}>.**",
        color=discord.Color.blue(),
    ),
    "MOVED": lambda ctx, **kwargs: discord.Embed(
        title="",
        description=f"**:wheelchair: Moving to <#{kwargs.get('channel_id')}>**",
        color=discord.Color.blue(),
    ),
    "CURRENT_VOLUME": lambda ctx, **kwargs: discord.Embed(
        title="",
        description=f"**🔊 `{kwargs.get('volume')}%`**",
        color=discord.Color.blue(),
    ),
    "SPEED_CHANGED": lambda ctx, **kwargs: discord.Embed(
        title="",
        description=f"**:stopwatch:  Speed increased by `{kwargs.get('multiplier')}x`**",
        color=discord.Color.blue(),
    ),
    "EFFECTS_CLEARED": lambda ctx: discord.Embed(
        title="",
        description="**:microphone:  Effects were cleared.**",
        color=discord.Color.blue(),
        footer=discord.EmbedFooter(text="takes 3 seconds to apply"),
    ),
    "NODE_CONNECT_SUCCESS": lambda ctx, **kwargs: discord.Embed(
        title="",
        description=f"**✅ Connected to node `{kwargs.get('uri')}`**",
        color=discord.Color.blue(),
    ),
    "NODE_RECONNECT_TO_PLAYER_SUCCESS": lambda ctx, **kwargs: discord.Embed(
        title="",
        description=f"**✅ Reconnected your player to node `{kwargs.get('uri')}`**",
        color=discord.Color.blue(),
    ),
    "NODE_RECONNECT_SUCCESS": lambda ctx, **kwargs: discord.Embed(
        title="",
        description=f"**✅ Reconnected to node `{kwargs.get('uri')}`**",
        color=discord.Color.blue(),
    ),
    "USER_DATA_GENERATED": lambda ctx, **kwargs: discord.Embed(
        title="",
        description=f"**:floppy_disk:  Generated user data.**",
        color=discord.Color.blue,
    ),
    "DB_ADDED": lambda ctx, **kwargs: discord.Embed(
        title="",
        description=f"✅ String `{kwargs.get('to_upload')}` was added to `{kwargs.get('collection_name')}`",
        color=discord.Color.blue(),
    ),
    "DB_REMOVED": lambda ctx, **kwargs: discord.Embed(
        title="",
        description=f"✅ String `{kwargs.get('to_remove')}` was removed from `{kwargs.get('collection_name')}`",
        color=discord.Color.blue(),
    ),
}


async def send_response(
    ctx: discord.ApplicationContext,
    response_code: str,
    ephemeral: bool = True,
    delete_after: int = None,
    **kwargs: Any,
) -> None:
    """
    Send a response embed to the context.

    Args:
        ctx: The application context
        response_code: The response code from RESPONSE_CODES
        ephemeral: Whether the response should be ephemeral
        delete_after: Time in seconds to delete the response after
        **kwargs: Additional arguments to pass to the response handler
    """
    if response_code not in RESPONSE_CODES:
        raise ValueError(f"Unknown response code: {response_code}")

    response_handler = RESPONSE_CODES[response_code]
    embed = response_handler(ctx, **kwargs)
    await ctx.respond(embed=embed, ephemeral=ephemeral, delete_after=delete_after)
