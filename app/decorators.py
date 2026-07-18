from functools import wraps
from typing import Any, Callable, cast

import discord

from app.response_handler import make_embed, send


def is_joined() -> Callable[[Any], Any]:
    """Ensure the user and bot share a connected voice channel."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:  # pyright: ignore[reportAny]
            # args[0] is self and args[1] is ctx.
            ctx = cast(discord.Interaction, args[1])
            if not ctx.user.voice or not ctx.user.voice.channel:  # pyright: ignore[reportUnknownMemberType]
                await send(ctx, code="NO_VOICE_CHANNEL")
                return None

            vc = ctx.guild.voice_client
            player_channel = getattr(vc, "channel", None) if vc else None
            if not vc or not player_channel:
                await send(
                    ctx,
                    embed=make_embed(":x: I'm not joined in a voice channel."),
                )
                return None

            if player_channel.id != ctx.user.voice.channel.id:  # pyright: ignore[reportAny, reportUnknownMemberType]
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
            player = ctx.guild.voice_client
            if not player or not player.current:  # pyright: ignore[reportUnknownMemberType]
                await send(
                    ctx,
                    embed=make_embed(
                        ":x: I'm not playing anything. Type `/music play` from vc."
                    ),
                )
                return None

            if player.channel.id != ctx.user.voice.channel.id:  # pyright: ignore[reportUnknownMemberType]
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
            player = ctx.guild.voice_client

            if not player or (not player.queue and not player.queue.autoplay_tracks):  # pyright: ignore[reportUnknownMemberType]
                await send(ctx, code="NO_TRACKS_IN_QUEUE")
                return None

            return await func(*args, **kwargs)  # pyright: ignore[reportAny]

        return wrapper

    return decorator
