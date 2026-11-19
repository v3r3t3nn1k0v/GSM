import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, Bot
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Chat, Message, TelegramObject, User

from app.config import Settings
from bot.users.keyboards import CHECK_SUBSCRIPTION_CB, subscription_keyboard
from bot.users.texts import SUBSCRIBE_REQUIRED_TEXT

logger = logging.getLogger(__name__)

_SUBSCRIBED_STATUSES = {
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.CREATOR,
}


async def is_subscriber(bot: Bot, channel_id: str, user_id: int) -> bool | None:
    """Подписан ли пользователь на канал; None — не удалось проверить (ошибка API)."""
    try:
        member = await bot.get_chat_member(channel_id, user_id)
    except TelegramAPIError as exc:
        logger.error("Не удалось проверить подписку %s на %s: %r", user_id, channel_id, exc)
        return None
    if member.status in _SUBSCRIBED_STATUSES:
        return True
    # Ограниченный участник формально остаётся в канале
    return member.status == ChatMemberStatus.RESTRICTED and bool(member.is_member)


class SubscriptionMiddleware(BaseMiddleware):
    """Не пускает в бота пользователей без подписки на канал.

    Вешается как outer-middleware на message и callback_query: вместо хендлеров
    незнакомец получает сообщение с кнопками «Подписаться» / «Я подписался».
    Админы бота и сама кнопка проверки подписку не требуют.
    """

    def __init__(self, settings: Settings) -> None:
        self._channel_id = settings.telegram_channel_id
        self._channel_url = settings.channel_url
        self._admin_ids = set(settings.admin_ids)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not self._channel_id:  # проверка выключена
            return await handler(event, data)

        user: User | None = data.get("event_from_user")
        chat: Chat | None = data.get("event_chat")
        # Без пользователя (посты в канале и пр.) и вне лички не проверяем
        if user is None or user.is_bot or (chat is not None and chat.type != ChatType.PRIVATE):
            return await handler(event, data)
        if user.id in self._admin_ids or (
            isinstance(event, CallbackQuery) and event.data == CHECK_SUBSCRIPTION_CB
        ):
            return await handler(event, data)

        subscribed = await is_subscriber(data["bot"], self._channel_id, user.id)
        if subscribed is None or subscribed:
            # None (API недоступен) — пускаем, чтобы сбой не заблокировал бота целиком
            return await handler(event, data)

        await self._ask_to_subscribe(event)
        return None  # до хендлеров не доходим

    async def _ask_to_subscribe(self, event: TelegramObject) -> None:
        """Показываем сообщение-заглушку с кнопками подписки."""
        keyboard = subscription_keyboard(self._channel_url)
        if isinstance(event, CallbackQuery):
            await event.answer("Сначала подпишитесь на канал 🔒", show_alert=True)
            if event.message is not None:
                await event.message.answer(SUBSCRIBE_REQUIRED_TEXT, reply_markup=keyboard)
        elif isinstance(event, Message):
            await event.answer(SUBSCRIBE_REQUIRED_TEXT, reply_markup=keyboard)
