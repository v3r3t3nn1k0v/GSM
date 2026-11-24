from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Колбэк кнопки «Я подписался» (см. SubscriptionMiddleware)
CHECK_SUBSCRIPTION_CB = "users:check_subscription"

# Ответы на стартовый вопрос о личных целях
ROLE_YES_CB = "users:role:yes"
ROLE_NO_CB = "users:role:no"


def role_keyboard() -> InlineKeyboardMarkup:
    """Стартовый вопрос «для личных целей?»: да — заявка, нет — ветка агента."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да", callback_data=ROLE_YES_CB)
    builder.button(text="❌ Нет", callback_data=ROLE_NO_CB)
    builder.adjust(2)
    return builder.as_markup()


def subscription_keyboard(channel_url: str) -> InlineKeyboardMarkup:
    """Заглушка для неподписанных: ссылка на канал + проверка подписки."""
    builder = InlineKeyboardBuilder()
    if channel_url:
        builder.button(text="📢 Подписаться на канал", url=channel_url)
    builder.button(text="✅ Я подписался", callback_data=CHECK_SUBSCRIPTION_CB)
    builder.adjust(1)
    return builder.as_markup()
