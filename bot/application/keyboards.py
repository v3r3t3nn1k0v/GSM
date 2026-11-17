from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

START_APPLICATION_CB = "application:start"

FUEL_AI = "АИ"
FUEL_DT = "ДТ"


class FuelTypeCallback(CallbackData, prefix="fuel"):
    """Выбор вида топлива для конкретной заявки (защита от старых кнопок)."""

    application_id: int
    value: str


class ProcessedCallback(CallbackData, prefix="appdone"):
    """Кнопка «Заявка обработана» в сообщении менеджеру."""

    application_id: int


def processed_keyboard(application_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Заявка обработана",
        callback_data=ProcessedCallback(application_id=application_id),
    )
    return builder.as_markup()


def share_contact_keyboard() -> ReplyKeyboardMarkup:
    """Reply-клавиатура с кнопкой передачи контакта (вопрос о телефоне)."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Поделиться контактом", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def reply_keyboard_done() -> ReplyKeyboardMarkup:
    """Убираем reply-клавиатуру после ответа."""
    return ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)


def fuel_type_keyboard(application_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"⛽ {FUEL_AI}",
        callback_data=FuelTypeCallback(application_id=application_id, value=FUEL_AI),
    )
    builder.button(
        text=f"🚛 {FUEL_DT}",
        callback_data=FuelTypeCallback(application_id=application_id, value=FUEL_DT),
    )
    builder.adjust(2)
    return builder.as_markup()
