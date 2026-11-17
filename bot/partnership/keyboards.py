from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import get_settings
from bot.application.keyboards import START_APPLICATION_CB

PARTNERSHIP_OFFER_CB = "partnership:offer"


class PartnershipCallback(CallbackData, prefix="partner"):
    """Ответ на предложение партнёрской программы."""

    accept: bool


def partnership_keyboard() -> InlineKeyboardMarkup:
    """Да/нет под предложением партнёрской программы."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Да, интересно", callback_data=PartnershipCallback(accept=True)
    )
    builder.button(
        text="❌ Нет, спасибо", callback_data=PartnershipCallback(accept=False)
    )
    builder.adjust(2)
    return builder.as_markup()


def subscribe_keyboard() -> InlineKeyboardMarkup | None:
    """Кнопка-ссылка на канал (если CHANNEL_URL задан)."""
    channel_url = get_settings().channel_url
    if not channel_url:
        return None
    builder = InlineKeyboardBuilder()
    builder.button(text="📢 Подписаться на канал", url=channel_url)
    return builder.as_markup()


def back_to_application_keyboard() -> InlineKeyboardMarkup:
    """Возврат в основную воронку после отправки PDF."""
    builder = InlineKeyboardBuilder()
    builder.button(text="⛽ Заполнить заявку", callback_data=START_APPLICATION_CB)
    return builder.as_markup()
