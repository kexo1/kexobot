from functools import wraps
from typing import Any, Callable, Protocol

from app.response_handler import make_embed, send


class CommandFunc(Protocol):
    async def __call__(self, *args: Any, **kwargs: Any) -> Any: ...


def is_joined() -> Callable[[CommandFunc], CommandFunc]:
    """Ensure the user and bot share a connected voice channel."""

    def decorator(func: CommandFunc) -> CommandFunc:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # args[0] is self and args[1] is ctx.
            ctx = args[1]
            if not ctx.user.voice or not ctx.user.voice.channel:
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

            if player_channel.id != ctx.user.voice.channel.id:
                await send(ctx, code="NOT_IN_SAME_VOICE_CHANNEL")
                return None

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def is_playing() -> Callable[[CommandFunc], CommandFunc]:
    """Ensure a track is playing and user shares the voice channel."""

    def decorator(func: CommandFunc) -> CommandFunc:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            ctx = args[1]
            vc = ctx.guild.voice_client
            if not vc or not vc.current:
                await send(
                    ctx,
                    embed=make_embed(
                        ":x: I'm not playing anything. Type `/music play` from vc."
                    ),
                )
                return None

            if ctx.guild.voice_client.channel.id != ctx.user.voice.channel.id:
                await send(ctx, code="NOT_IN_SAME_VOICE_CHANNEL")
                return None

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def is_queue_empty() -> Callable[[CommandFunc], CommandFunc]:
    """Ensure the queue is not empty."""

    def decorator(func: CommandFunc) -> CommandFunc:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            ctx = args[1]
            vc = ctx.guild.voice_client

            if not vc or (not vc.queue and not vc.queue.autoplay_tracks):
                await send(ctx, code="NO_TRACKS_IN_QUEUE")
                return None

            return await func(*args, **kwargs)

        return wrapper

    return decorator
