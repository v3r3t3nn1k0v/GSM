from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.application.keyboards import START_APPLICATION_CB
from bot.partnership.keyboards import PARTNERSHIP_OFFER_CB

# Колбэк кнопки «Я подписался» (см. SubscriptionMiddleware)
CHECK_SUBSCRIPTION_CB = "users:check_subscription"


def start_keyboard() -> InlineKeyboardMarkup:
    """Стартовая развилка: заявка или партнёрская программа."""
    builder = InlineKeyboardBuilder()
    builder.button(text="⛽ Заполнить заявку", callback_data=START_APPLICATION_CB)
    builder.button(
        text="🤝 Партнёрская программа", callback_data=PARTNERSHIP_OFFER_CB
    )
    builder.adjust(1)
    return builder.as_markup()


def subscription_keyboard(channel_url: str) -> InlineKeyboardMarkup:
    """Заглушка для неподписанных: ссылка на канал + проверка подписки."""
    builder = InlineKeyboardBuilder()
    if channel_url:
        builder.button(text="📢 Подписаться на канал", url=channel_url)
    builder.button(text="✅ Я подписался", callback_data=CHECK_SUBSCRIPTION_CB)
    builder.adjust(1)
    return builder.as_markup()
