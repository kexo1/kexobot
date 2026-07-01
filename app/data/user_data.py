"""Manager for persistent user data."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.data.base import BaseDataManager
from app.data.models import UserData

if TYPE_CHECKING:
    from app.main import KexoBotClient


class UserDataManager(BaseDataManager[UserData]):
    """Manager for persistent user data stored in MongoDB."""

    def __init__(self, collection, bot: KexoBotClient) -> None:
        super().__init__(collection, UserData)
        self._bot = bot
