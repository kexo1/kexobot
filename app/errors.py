from typing import Dict, Callable, Any
import discord

ErrorHandler = Callable[[discord.ApplicationContext, ...], discord.Embed]

ERROR_CODES: Dict[str, ErrorHandler] = {
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
    "NOT_PLAYING": lambda ctx: discord.Embed(
        title="",
        description=f":x: I'm not playing anything. Type `/play` from vc.",
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
    "CONNECTION_TIMEOUT": lambda ctx: discord.Embed(
        title="",
        description=":x: Failed to connect to the voice channel, was bot moved manually? If yes disconnect it and try "
                    "again.",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "NODE_UNRESPONSIVE": lambda ctx: discord.Embed(
        title="",
        description=":x: Node is unresponsive, please use command `/reconnect_node`",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "NO_TRACKS": lambda ctx, search: discord.Embed(
        title="",
        description=f":x: No tracks were found for `{search}`.",
        color=discord.Color.blue(),
    ),
    "NO_TRACKS_IN_QUEUE": lambda ctx: discord.Embed(
        title="",
        description="Queue is empty.",
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
    "CHANNEL_NOT_NSF": lambda ctx: discord.Embed(
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
    "DB_ALREADY_IN_LIST": lambda ctx, to_upload: discord.Embed(
        title="",
        description=f":x: String `{to_upload}` is already in the list, use `/bot_config show`",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
    "DB_NOT_IN_LIST": lambda ctx, to_remove: discord.Embed(
        title="",
        description=f":x: String `{to_remove}` is not in the list, use `/bot_config show`",
        color=discord.Color.from_rgb(r=220, g=0, b=0),
    ),
}


async def send_error(
    ctx: discord.ApplicationContext,
    error_code: str,
    ephemeral: bool = True,
    **kwargs: Any,
) -> None:
    """
    Send an error embed to the context.

    Args:
        ctx: The application context
        error_code: The error code from ERROR_CODES
        ephemeral: Whether the response should be ephemeral
        **kwargs: Additional arguments to pass to the error handler
    """
    if error_code not in ERROR_CODES:
        raise ValueError(f"Unknown error code: {error_code}")

    error_handler = ERROR_CODES[error_code]
    embed = error_handler(ctx, **kwargs)
    await ctx.respond(embed=embed, ephemeral=ephemeral)
