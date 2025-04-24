from functools import wraps

from app.utils import find_track
from app.errors import send_error


def is_joined():
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # args[0] is self and args[1] is ctx.
            ctx = args[1]
            if not ctx.author.voice or not ctx.author.voice.channel:
                await send_error(ctx, "NO_VOICE_CHANNEL")

            vc = ctx.voice_client

            if not vc or not getattr(vc, "_connected", False):
                await send_error(ctx, "NOT_IN_VOICE_CHANNEL")

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def is_playing():
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            ctx = args[1]
            vc = ctx.voice_client
            if not vc or not vc.playing or not vc.current:
                await send_error(ctx, "NOT_PLAYING")
                return

            if ctx.voice_client.channel.id != ctx.author.voice.channel.id:
                await send_error(ctx, "NOT_IN_SAME_VOICE_CHANNEL")

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def is_queue_empty():
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            ctx = args[1]
            vc = ctx.voice_client
            if not vc or not vc.queue:
                await send_error(ctx, "NO_TRACKS_IN_QUEUE")
                return

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def is_song_in_queue():
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            ctx = args[1]
            to_find = kwargs["to_find"]
            player = ctx.voice_client

            if not find_track(player, to_find):
                await send_error(ctx, "NO_TRACKS", search=to_find)
                return

            return await func(*args, **kwargs)

        return wrapper

    return decorator
