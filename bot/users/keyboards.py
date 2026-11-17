from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.application.keyboards import START_APPLICATION_CB
from bot.partnership.keyboards import PARTNERSHIP_OFFER_CB


def start_keyboard() -> InlineKeyboardMarkup:
    """Стартовая развилка: заявка или партнёрская программа."""
    builder = InlineKeyboardBuilder()
    builder.button(text="⛽ Заполнить заявку", callback_data=START_APPLICATION_CB)
    builder.button(
        text="🤝 Партнёрская программа", callback_data=PARTNERSHIP_OFFER_CB
    )
    builder.adjust(1)
    return builder.as_markup()
