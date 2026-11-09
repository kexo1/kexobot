from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, cast

import discord
import sonolink
from sonolink import models as sl_models
from sonolink.models import AutoPlaySettings, HistorySettings

from app.config.colors import COLOR_BLUE, COLOR_RED, COLOR_YELLOW
from app.config.music import MUSIC_SOURCES
from app.player_types import caller_voice_channel, get_player, guild_of, member_of
from app.response_handler import defer_interaction, make_embed, send
from app.utils import fix_audio_title, make_now_playing_embed

if TYPE_CHECKING:
    from app.client import KexoBotClient

logger = logging.getLogger(__name__)


def get_search_prefix(query: str) -> str | None:
    """Get the search prefix for a given query."""
    for pattern, prefix in MUSIC_SOURCES:
        if pattern.search(query):
            return prefix
    return None


def set_track_requester(
    track: sl_models.Playable,
    user: discord.abc.User,
) -> None:
    track.extras.requester_name = user.name
    avatar = getattr(getattr(user, "display_avatar", None), "url", None)
    if avatar:
        track.extras.requester_avatar = avatar


def make_added_to_queue_embed(track: sl_models.Playable) -> discord.Embed:
    return discord.Embed(
        title="",
        description=f"**Added to queue:\n [{fix_audio_title(track)}]({track.uri})**",
        color=COLOR_BLUE,
    )


async def fetch_first_track(
    ctx: discord.Interaction,
    tracks: sl_models.SearchResult
    | sl_models.Playlist
    | sl_models.Playable
    | list[sl_models.Playable],
) -> sl_models.Playable | None:
    player = get_player(ctx)

    # Unwrap SearchResult
    resolved = tracks.result if isinstance(tracks, sl_models.SearchResult) else tracks

    # Handle Playlist
    if isinstance(resolved, sl_models.Playlist):
        return await _handle_playlist(ctx, player, resolved)

    # Handle single Playable
    if isinstance(resolved, sl_models.Playable):
        set_track_requester(resolved, ctx.user)
        return resolved

    if not resolved:
        return None

    first_track = resolved[0]
    set_track_requester(first_track, ctx.user)
    return first_track


async def _handle_playlist(
    ctx: discord.Interaction,
    player: sonolink.Player,
    playlist: sl_models.Playlist,
) -> sl_models.Playable:
    for track in playlist:
        set_track_requester(track, ctx.user)

    first_track = playlist.tracks.pop(0)
    song_count = player.queue.put(playlist)

    embed = discord.Embed(
        title="",
        description=f"Added the playlist **`{playlist.name}`** ({song_count} songs) to the queue.",
        color=COLOR_BLUE,
    )

    await send(ctx, embed=embed)
    return first_track


async def should_move_to_channel(ctx: discord.Interaction) -> bool:
    player = get_player(ctx)
    target_channel = caller_voice_channel(ctx)
    if player and player.channel.id == target_channel.id:
        return True

    if player.current:
        await send(
            ctx,
            embed=make_embed(
                ":x: I am playing in a different voice channel, wait till the song finishes."
            ),
        )
        return False

    await player.guild.change_voice_state(channel=target_channel)
    await send(
        ctx,
        embed=make_embed(f":wheelchair: Moving to <#{target_channel.id}>"),
        ephemeral=False,
    )
    return True


class MusicPlaybackService:
    def __init__(self, bot: KexoBotClient) -> None:
        self._bot = bot

    async def execute_play(
        self,
        ctx: discord.Interaction,
        search: str,
        play_next: bool = False,
    ) -> None:
        """Shared play flow used by /music play and radio commands."""
        await defer_interaction(ctx)

        if self._bot.node_is_switching.get(guild_of(ctx).id, False):
            await send(
                ctx,
                embed=make_embed(
                    ":hourglass_flowing_sand: Please wait until the bot finishes switching nodes.",
                    color=COLOR_YELLOW,
                ),
            )
            return

        if not self._bot.node:
            await send(ctx, code="NODE_NOT_FOUND", ephemeral=False)
            return

        if not get_player(ctx):
            joined: bool = await self._join_channel(ctx)

            if not joined:
                return

            await self._prepare_sonolink(ctx)

        is_moved: bool = await should_move_to_channel(ctx)
        if not is_moved:
            return

        player = get_player(ctx)

        tracks = await self._search_tracks(ctx, search)
        if not tracks:
            return

        track = await fetch_first_track(ctx, tracks)
        if not track:
            return

        player.temp_current = track  # To be used in case of switching nodes

        if player.current:
            if play_next:
                player.queue.put_at(0, track)
            else:
                player.queue.put(track)

            await send(ctx, embed=make_added_to_queue_embed(track))
            return

        player._now_playing_sent = True  # Prevent listener from duplicating
        await send(ctx, embed=make_now_playing_embed(track))
        await self._play_track(ctx, track)

    async def _search_tracks(
        self, ctx: discord.Interaction, search: str
    ) -> (
        sl_models.SearchResult
        | sl_models.Playlist
        | sl_models.Playable
        | list[sl_models.Playable]
        | None
    ):
        source = get_search_prefix(search)
        # If it's not a URL with a recognizable prefix, default to YouTube search
        if source is None:
            if search.startswith(("http://", "https://")):
                source = None
            else:
                source = "ytsearch"

        # Prefer youtube over spotify, but if youtube fails, try spotify
        if source == "spsearch":
            spotify_search = True
            source = "ytsearch"
        else:
            spotify_search = False

        player = get_player(ctx)

        for i in range(2):
            try:
                tracks: sl_models.SearchResult = await asyncio.wait_for(
                    self._bot.sonolink_client.search_track(
                        search, source=cast("str", source)
                    ),
                    timeout=20,
                )
                if not tracks.is_error() and not tracks.is_empty() and tracks.result:
                    return tracks

                if spotify_search:
                    # Keep one lightweight fallback without switching nodes.
                    tracks = await asyncio.wait_for(
                        self._bot.sonolink_client.search_track(
                            search, source="spsearch"
                        ),
                        timeout=5,
                    )
                    if (
                        not tracks.is_error()
                        and not tracks.is_empty()
                        and tracks.result
                    ):
                        return tracks

            except TimeoutError:
                if i == 0:
                    await send(
                        ctx,
                        embed=make_embed(
                            ":warning: Node timed out finding tracks, switching to another node.",
                            color=COLOR_YELLOW,
                        ),
                        ephemeral=False,
                    )
                await self._bot.state.switch_node(
                    player=player,
                    search_callback=lambda: self._bot.sonolink_client.search_track(
                        search, source=cast("str", source)
                    ),
                    send_failure_message=False,
                )
                continue

            except Exception as e:  # noqa: BLE001
                await send(
                    ctx,
                    embed=make_embed(
                        ":x: Failed to load tracks. You likely entered a wrong link or "
                        "this Lavalink server lacks necessary plugins.\n"
                        "Try using command `/node reconnect`",
                        color=COLOR_RED,
                    ),
                    ephemeral=False,
                )
                logger.error("[sonolink] Error searching for tracks: %s", e)
                return None

        await send(
            ctx,
            code="NO_TRACKS_FOUND",
            ephemeral=False,
            search=search,
        )
        return None

    async def _join_channel(self, ctx: discord.Interaction) -> bool:
        member = member_of(ctx)
        if not member.voice or not member.voice.channel:
            await send(ctx, code="NO_VOICE_CHANNEL")
            return False

        channel = member.voice.channel
        guild = await self._bot.guild_data_manager.get(guild_of(ctx).id)
        autoplay_mode = (
            sonolink.AutoPlayMode.PARTIAL
            if guild.music.autoplay_mode == 1
            else sonolink.AutoPlayMode.ENABLED
        )

        last_error: Exception | None = None
        failed_uris: set[str] = set()
        node = self._bot.node

        if node is None:
            await send(ctx, code="NODE_NOT_FOUND", ephemeral=False)
            return False

        try:
            player_cls = self._build_player_class(node, autoplay_mode)
            await channel.connect(cls=player_cls, timeout=10)
            return True

        except (discord.Forbidden, discord.ClientException):
            await send(ctx, code="NO_PERMISSIONS", ephemeral=False)
            return False

        except Exception as e:  # noqa: BLE001
            last_error = e
            failed_uris.add(node.uri)
            self._bot.state.change_node_score(node.uri, -20)
            logger.warning(
                "[Sonolink] Voice connect failed for node %s: %s",
                node.uri,
                e,
            )

        await send(
            ctx,
            embed=make_embed(
                ":x: Failed to connect to voice channel, try again later.",
                color=COLOR_RED,
            ),
            ephemeral=False,
        )
        if last_error:
            logger.error(
                "[Sonolink] Error connecting to voice channel: %s",
                last_error,
            )

        return False

    def _build_player_class(
        self,
        node: sonolink.Node,
        autoplay_mode: sonolink.AutoPlayMode = sonolink.AutoPlayMode.PARTIAL,
    ):
        return node.create_player(
            autoplay_settings=AutoPlaySettings(
                mode=autoplay_mode,
                discovery_count=10,
            ),
            history_settings=HistorySettings(
                enabled=True,
                max_items=16,
            ),
        )

    async def _play_track(
        self, ctx: discord.Interaction, track: sl_models.Playable
    ) -> bool:
        player = get_player(ctx)
        for i in range(3):
            try:
                await player.play(track)
                break
            except Exception as e:  # noqa: BLE001
                logger.error(
                    f"[sonolink] {i + 1}. Error playing track, retrying: %s", e
                )

        set_track_requester(track, ctx.user)
        return True

    async def _prepare_sonolink(self, ctx: discord.Interaction) -> None:
        player = get_player(ctx)
        player.text_channel = cast("discord.abc.MessageableChannel", ctx.channel)

        guild = await self._bot.guild_data_manager.get(guild_of(ctx).id)
        volume = guild.music.volume
        try:
            await player.set_volume(volume)
        except Exception as e:
            if "Session not found" not in str(e):
                raise

            await self._bot.state.switch_node(
                player=player,
                send_success_message=False,
                send_failure_message=False,
            )
            await player.set_volume(volume)

        await send(
            ctx,
            embed=make_embed(
                f"Joined <#{player.channel.id}>, text channel set to <#{player.text_channel.id}>."
            ),
            ephemeral=False,
        )
