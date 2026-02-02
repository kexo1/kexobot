from functools import wraps
from typing import Any, Callable, Protocol

from app.response_handler import send_response


class CommandFunc(Protocol):
    async def __call__(self, *args: Any, **kwargs: Any) -> Any: ...


def is_joined() -> Callable[[CommandFunc], CommandFunc]:
    """Ensure the user and bot share a connected voice channel."""

    def decorator(func: CommandFunc) -> CommandFunc:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # args[0] is self and args[1] is ctx.
            ctx = args[1]
            if not ctx.author.voice or not ctx.author.voice.channel:
                await send_response(ctx, "NO_VOICE_CHANNEL")
                return None

            vc = ctx.voice_client
            if not vc or not getattr(vc, "_connected", False):
                await send_response(ctx, "NOT_IN_VOICE_CHANNEL")
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
            vc = ctx.voice_client
            if not vc or not vc.playing or not vc.current:
                await send_response(ctx, "NOT_PLAYING")
                return None

            if ctx.voice_client.channel.id != ctx.author.voice.channel.id:
                await send_response(ctx, "NOT_IN_SAME_VOICE_CHANNEL")
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
            vc = ctx.voice_client
            if not vc or not vc.queue:
                await send_response(ctx, "NO_TRACKS_IN_QUEUE")
                return None

            return await func(*args, **kwargs)

        return wrapper

    return decorator
