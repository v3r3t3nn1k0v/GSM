from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Колбэк кнопки «Я подписался» (см. SubscriptionMiddleware)
CHECK_SUBSCRIPTION_CB = "users:check_subscription"

# Варианты входа в бота
ROLE_CONSUMER_CB = "users:role:consumer"
ROLE_NEWS_CB = "users:role:news"


def role_keyboard() -> InlineKeyboardMarkup:
    """Стартовый выбор: топливо для бизнеса или новости."""
    builder = InlineKeyboardBuilder()
    builder.button(text="⛽ Топливо для бизнеса или работы", callback_data=ROLE_CONSUMER_CB)
    builder.button(text="📰 Новости про топливо", callback_data=ROLE_NEWS_CB)
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
