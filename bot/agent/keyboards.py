from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import get_settings

AGENT_YES_CB = "agent:yes"
AGENT_NO_CB = "agent:no"


class AgentAnswerCallback(CallbackData, prefix="agent"):
    """Ответ на предложение стать агентом."""

    accept: bool


def agent_offer_keyboard() -> InlineKeyboardMarkup:
    """Да/нет под предложением стать агентом."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Да, стать агентом", callback_data=AgentAnswerCallback(accept=True)
    )
    builder.button(text="❌ Нет, спасибо", callback_data=AgentAnswerCallback(accept=False))
    builder.adjust(2)
    return builder.as_markup()


def channel_keyboard() -> InlineKeyboardMarkup | None:
    """Кнопка-ссылка на канал (если CHANNEL_URL задан)."""
    channel_url = get_settings().channel_url
    if not channel_url:
        return None
    builder = InlineKeyboardBuilder()
    builder.button(text="📢 Подписаться на канал", url=channel_url)
    return builder.as_markup()
