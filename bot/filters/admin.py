from typing import Any, Awaitable, Callable, Dict

from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from app.config import get_settings


class IsAdmin(BaseFilter):
    """Пропускает события только от пользователей из ADMIN_IDS."""

    async def __call__(self, event: TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        return bool(user and user.id in get_settings().admin_ids)
