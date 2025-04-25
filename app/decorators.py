from functools import wraps

from app.response_handler import send_response


def is_joined():
    def decorator(func) -> None:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> None:
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


def is_playing():
    def decorator(func) -> None:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> None:
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


def is_queue_empty():
    def decorator(func) -> None:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> None:
            ctx = args[1]
            vc = ctx.voice_client
            if not vc or not vc.queue:
                await send_response(ctx, "NO_TRACKS_IN_QUEUE")
                return None

            return await func(*args, **kwargs)

        return wrapper

    return decorator
