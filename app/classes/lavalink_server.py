import logging
from typing import TYPE_CHECKING, Any, TypeGuard, cast

import httpx

from app.config.mongo import DB_CACHE
from app.config.music import LAVALINK_URL
from app.config.scraping import API_LAVALIST
from app.utils import get_url_response_time, make_http_request

logger = logging.getLogger(__name__)


def _is_json_object(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    fields: dict[object, object] = cast(dict[object, object], value)
    return all(isinstance(key, str) for key in fields)


if TYPE_CHECKING:
    from app.client import KexoBotClient


def get_full_node_url(host: str, port: int, secure: bool = False) -> str:
    """Construct a full Lavalink node URL."""
    protocol = "https" if secure else "http"
    return f"{protocol}://{host}:{port}"


class LavalinkServerManager:
    """Class to manage lavalink servers. Checks from various sources and returns
    a list of lavalink servers.

    It also checks if the server is online or offline and if it is a low quality node.
    The class is used to get lavalink servers from lavalist and lavainfo GitHub.

    Parameters
    ----------
    session: :class:`httpx.AsyncClient`
        HTTP client for making requests.
    offline_lavalink_servers: list[str]
        List of offline lavalink servers.
    """

    def __init__(self, bot: "KexoBotClient", session: httpx.AsyncClient) -> None:
        self._bot = bot
        self._session = session
        self._cached_lavalink_servers = self._bot.cached_lavalink_servers
        self._fresh_nodes: set[str] = set()

    async def _fetch_and_parse(self, api_url: str) -> list[dict[str, Any]] | None:
        json_data = await make_http_request(self._session, api_url, get_json=True)
        if not isinstance(json_data, list):
            return None

        records = cast(list[object], json_data)
        servers = [item for item in records if _is_json_object(item)]
        if servers:
            await self._parse_lavalink_servers(servers)
        return servers

    async def fetch(self) -> None:
        """Get new Lavalink servers from Lavainfo GitHub and Lavalist.
        If both sources are available, update the cache and clear removed nodes.
        """
        json_data_first = await self._fetch_and_parse(API_LAVALIST)

        # Only update cache and clear removed nodes if both sources are available.
        # Otherwise we might end up with an empty or incomplete list of nodes.
        if json_data_first:
            self._clear_removed_nodes()
            await self._bot.config_manager.save("lavalink_servers", DB_CACHE)
            logger.info("[Lavalink] Lavalink servers list got updated, updating cache.")

    async def _parse_lavalink_servers(
        self,
        json_data: list[dict[str, Any]],
    ) -> None:
        for server in json_data:
            host = server.get("host")
            port = server.get("port")
            password = server.get("password")
            if (
                not isinstance(host, str)
                or not isinstance(port, int)
                or not isinstance(password, str)
            ):
                continue

            rest_version = server.get("restVersion")
            version = server.get("version")
            if (
                (rest_version is not None and rest_version != "v4")
                or (version is not None and version != "v4")
                or "nodelink" in host
            ):
                continue

            uri = get_full_node_url(
                host,
                port,
                server.get("secure") is True,
            )
            self._fresh_nodes.add(uri)

            if uri in self._cached_lavalink_servers:
                continue

            ping = await get_url_response_time(self._session, uri)
            self._cached_lavalink_servers[uri] = {
                "password": password,
                "score": 0,
                "ping": ping,
            }

    def _clear_removed_nodes(self) -> None:
        """Method to clear old nodes from the cached lavalink servers."""
        self._fresh_nodes.add(LAVALINK_URL)

        for uri in list(self._cached_lavalink_servers.keys()):
            if uri not in self._fresh_nodes:
                self._cached_lavalink_servers.pop(uri, None)
