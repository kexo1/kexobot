from functools import wraps
from typing import Any, Callable, cast

import discord

from app.player_types import caller_voice_channel_id, get_player, member_of
from app.response_handler import make_embed, send


def is_joined() -> Callable[[Any], Any]:
    """Ensure the user and bot share a connected voice channel."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:  # pyright: ignore[reportAny]
            # args[0] is self and args[1] is ctx.
            ctx = cast(discord.Interaction, args[1])
            member = member_of(ctx)
            if not member.voice or not member.voice.channel:
                await send(ctx, code="NO_VOICE_CHANNEL")
                return None

            player = get_player(ctx)
            if not player or not player.channel:
                await send(
                    ctx,
                    embed=make_embed(":x: I'm not joined in a voice channel."),
                )
                return None

            if player.channel.id != member.voice.channel.id:
                await send(ctx, code="NOT_IN_SAME_VOICE_CHANNEL")
                return None

            return await func(*args, **kwargs)  # pyright: ignore[reportAny]

        return wrapper

    return decorator


def is_playing() -> Callable[[Any], Any]:
    """Ensure a track is playing and user shares the voice channel."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:  # pyright: ignore[reportAny]
            ctx = cast(discord.Interaction, args[1])
            player = get_player(ctx)
            if not player or not player.current:
                await send(
                    ctx,
                    embed=make_embed(
                        ":x: I'm not playing anything. Type `/music play` from vc."
                    ),
                )
                return None

            if player.channel.id != caller_voice_channel_id(ctx):
                await send(ctx, code="NOT_IN_SAME_VOICE_CHANNEL")
                return None

            return await func(*args, **kwargs)  # pyright: ignore[reportAny]

        return wrapper

    return decorator


def is_queue_empty() -> Callable[[Any], Any]:
    """Ensure the queue is not empty."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:  # pyright: ignore[reportAny]
            ctx = cast(discord.Interaction, args[1])
            player = get_player(ctx)

            if not player or (not player.queue and not player.queue.autoplay_tracks):
                await send(ctx, code="NO_TRACKS_IN_QUEUE")
                return None

            return await func(*args, **kwargs)  # pyright: ignore[reportAny]

        return wrapper

    return decorator
