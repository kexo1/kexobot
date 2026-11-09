from __future__ import annotations

import asyncio
from typing import Protocol

from discord.ext import tasks

from app.client import KexoBotClient


class _Runtime(Protocol):
    async def main_loop(self) -> None: ...

    async def hourly_loop(self) -> None: ...


class BotBackgroundTasks:
    """Own the scheduled loops that run bot maintenance and feed updates."""

    def __init__(self, bot: KexoBotClient, runtime: _Runtime) -> None:
        self._bot = bot
        self._runtime = runtime

    @tasks.loop(minutes=1)
    async def main_loop(self) -> None:
        await self._runtime.main_loop()

    @main_loop.before_loop
    async def before_main_loop(self) -> None:
        await self._bot.wait_until_ready()

    @tasks.loop(hours=1)
    async def hourly_loop(self) -> None:
        await self._runtime.hourly_loop()

    @hourly_loop.before_loop
    async def before_hourly_loop(self) -> None:
        await self._bot.wait_until_ready()

    def start(self) -> None:
        self.main_loop.start()
        self.hourly_loop.start()

    async def stop(self) -> None:
        """Cancel scheduled loops and wait for their tasks to finish."""
        loops = (self.main_loop, self.hourly_loop)
        running_tasks = [
            task
            for loop in loops
            if (task := loop.get_task()) is not None and not task.done()
        ]

        for loop in loops:
            loop.cancel()

        results = await asyncio.gather(*running_tasks, return_exceptions=True)
        errors = [
            result
            for result in results
            if isinstance(result, Exception)
            and not isinstance(result, asyncio.CancelledError)
        ]
        if errors:
            raise ExceptionGroup("Background task shutdown failed", errors)
