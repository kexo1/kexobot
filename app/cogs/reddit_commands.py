from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

import asyncpraw.exceptions
import asyncpraw.models
import discord
from discord import app_commands
from discord.ext import commands

from app.config.colors import COLOR_BLUE, COLOR_GREEN
from app.config.reddit import SHITPOST_SUBREDDITS_ALL
from app.data import UserData
from app.response_handler import send

if TYPE_CHECKING:
    from app.client import KexoBotClient

logger = logging.getLogger(__name__)


class RedditCommands(commands.Cog):
    """Commands for configuring a user's Reddit feed."""

    slash_reddit = app_commands.Group(
        name="reddit", description="Commands for reddit posts"
    )

    def __init__(self, bot: KexoBotClient) -> None:
        self._bot = bot
        self._user_mgr = bot.user_data_manager

    @slash_reddit.command(
        name="settings",
        description="Change your list of subreddits.",
    )
    async def edit_subreddit(self, ctx: discord.Interaction) -> None:
        """Let the user configure subreddits and NSFW preference."""
        user_id = ctx.user.id
        user = await self._user_mgr.get(user_id)
        view = SubredditSelectorView(user_id, self._bot, user)

        embed = discord.Embed(
            title="Select Subreddits",
            description="Select the subreddits you want to see in shitpost command."
            " Currently selected subreddits are pre-checked.",
            color=COLOR_BLUE,
        )

        await send(ctx, embed=embed, view=view, ephemeral=True)


class SubredditSelectorView(discord.ui.View):
    """Interactive controls for editing a user's Reddit preferences."""

    def __init__(self, user_id: int, bot: KexoBotClient, user: UserData) -> None:
        super().__init__(timeout=600)
        self._user_id = user_id
        self.selected_subreddits: set[str] = set()
        self._bot = bot
        self._user = user
        self._user_mgr = bot.user_data_manager

        self._select = SubredditSelect(set(user.reddit.subreddits))
        self._save_button: discord.ui.Button[SubredditSelectorView] = discord.ui.Button(
            label="Save Changes",
            style=discord.ButtonStyle.green,
            custom_id="save_changes",
        )
        self._save_button.callback = self.save_changes

        nsfw_status = user.reddit.nsfw_posts
        self._nsfw_button: discord.ui.Button[SubredditSelectorView] = discord.ui.Button(
            label="NSFW ON" if nsfw_status else "NSFW OFF",
            style=(
                discord.ButtonStyle.green
                if not nsfw_status
                else discord.ButtonStyle.red
            ),
            custom_id="nsfw_posts",
        )
        self._nsfw_button.callback = self.nsfw_posts

        self.add_item(self._select)
        self.add_item(self._save_button)
        self.add_item(self._nsfw_button)

    async def nsfw_posts(self, interaction: discord.Interaction) -> None:
        """Toggle the user's NSFW preference."""
        self._user.reddit.nsfw_posts = not self._user.reddit.nsfw_posts
        await self._user_mgr.save(self._user_id, self._user)

        self._nsfw_button.label = (
            "NSFW ON" if self._user.reddit.nsfw_posts else "NSFW OFF"
        )
        self._nsfw_button.style = (
            discord.ButtonStyle.green
            if not self._user.reddit.nsfw_posts
            else discord.ButtonStyle.red
        )

        await interaction.response.edit_message(view=self)

    async def save_changes(self, interaction: discord.Interaction) -> None:
        """Persist the selected subreddits and update the user's multireddit."""
        if self.selected_subreddits:
            user = await self._user_mgr.get(self._user_id)
            user.reddit.subreddits = list(self.selected_subreddits)
            await self._user_mgr.save(self._user_id, user)

            if self._user_id in self._bot.temp_user_data_manager._cache:
                await self._update_multireddit()

        embed = discord.Embed(
            title="Changes Saved",
            description="Successfully updated your subreddit list"
            f" to `{len(self.selected_subreddits)}` subreddits.",
            color=COLOR_GREEN,
        )
        embed.set_footer(text="Message will be deleted in 20 seconds.")
        await interaction.response.edit_message(embed=embed, view=None, delete_after=20)

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True
        self.stop()

    async def _update_multireddit(self) -> None:
        temp = self._bot.temp_user_data_manager.get(self._user_id)
        multireddit = temp.reddit.multireddit
        if not multireddit:
            return
        multireddit = cast(asyncpraw.models.Multireddit, multireddit)
        await multireddit.load()
        added_subreddits: set[str] = set()

        for subreddit in multireddit.subreddits:
            if subreddit.display_name not in self.selected_subreddits:
                await multireddit.remove(subreddit)
                continue
            added_subreddits.add(subreddit.display_name)

        for subreddit in self.selected_subreddits:
            if subreddit in added_subreddits:
                continue

            try:
                await multireddit.add(await self._bot.reddit_agent.subreddit(subreddit))
            except asyncpraw.exceptions.RedditAPIException:
                logger.warning("[Reddit] Failed to add subreddit `%s`", subreddit)


class SubredditSelect(discord.ui.Select):
    """Select menu for choosing subreddits."""

    def __init__(self, current_subreddits: set[str]) -> None:
        options = [
            discord.SelectOption(
                label=f"r/{subreddit}",
                value=subreddit,
                default=subreddit in current_subreddits,
                description=f"Select to {'remove' if subreddit in current_subreddits else 'add'}"
                " this subreddit",
            )
            for subreddit in SHITPOST_SUBREDDITS_ALL
        ]

        super().__init__(
            placeholder="Select subreddits to toggle",
            max_values=len(SHITPOST_SUBREDDITS_ALL),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """Update selected subreddits from the user's selection."""
        view = cast(SubredditSelectorView, self.view)
        view.selected_subreddits = set(self.values)
        await interaction.response.defer()


async def setup(bot: KexoBotClient) -> None:
    """Register Reddit preference commands."""
    await bot.add_cog(RedditCommands(bot))
